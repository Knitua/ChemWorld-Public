"""One Codex process controls one complete ChemWorld experiment through file IPC."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from pathlib import Path
from typing import IO, Any, Protocol
from uuid import uuid4

from chemworld.agents.base import BaseAgent, HistoryRecord
from chemworld.agents.experiment_codex_ipc import (
    EXPERIMENT_CODEX_IPC_VERSION,
    ExperimentCodexIPCError,
    ExperimentCodexWorkspace,
    IPCRequest,
    diff_agent_snapshots,
)
from chemworld.agents.experiment_codex_mcp import MCP_SERVER_VERSION, SUPPORTED_TOOLS
from chemworld.agents.interaction import AgentDecisionContext, InteractionCapabilities
from chemworld.agents.prompt_context import compact_action, summarize_measurement
from chemworld.data.logging import to_builtin
from chemworld.providers.codex_subscription import (
    AUTH_SOURCE,
    HTTPS_PROVIDER_ID,
    MODEL_ACCESS_DATE,
    MODEL_SOURCE,
    SUPPORTED_MODELS,
)

INTERACTIVE_CODEX_EXPERIMENT_VERSION = "chemworld-interactive-codex-experiment-0.3"
DEFAULT_FINALIZATION_TIMEOUT_S = 300.0

_FINAL_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "status": {
            "type": "string",
            "enum": ["experiment_complete", "budget_exhausted", "stopped"],
        },
        "summary": {"type": "string", "maxLength": 2000},
    },
    "required": ["status", "summary"],
    "additionalProperties": False,
}

_SYSTEM_PROMPT = """You are the sole operation-level experimental agent in ChemWorld.
Complete one experiment by interacting with the environment only through the structured tools on
the required chemworld_lab MCP server. Call material_information once at the start. Submit every
physical operation with step, using the current expected_step and a complete action object. Use
the returned public outcome and state before selecting another operation. status exposes the
latest bounded state, history exposes only a bounded non-authoritative cache, and inspect_artifact
retrieves a bounded public characterization fragment only when useful.

The current working directory is agent/ and persists within this benchmark cell. You may create
any concise notes or data files here, but doing so is optional. The MCP server is host-owned and
outside the writable workspace; it exposes only bounded public evidence and operation outcomes.
The parent files ../.ipc/, ../public/, and ../reference/ are host-owned and outside your writable
root. The environment, resource limits, validation, and authoritative trajectory remain
host-owned. Do not
fabricate a tool result, repair an invalid action silently, or ask the host to terminate or assay
on your behalf. When the tool reports experiment_ended or budget_exhausted, stop calling lab
operations and return the requested final JSON. When the outcome is a discarded batch,
report that explicitly. Do not provide private chain-of-thought.

Campaign lifecycle completion is part of the task. When more than one vessel/final assay remains,
close every planned batch by final assay or an explicit discard; do not spend the whole shared pool
on the first batch. The public campaign_resources.lifecycle_reserve projection is advisory rather
than a hidden reservation, but treat its recommended remaining-attempt floor as a do-not-spend
floor for discretionary optimization. Stop optional diagnostics or repeated controls early enough
to preserve the current closeout and the minimum lifecycle of future batches.
"""


class InteractiveCodexExperimentError(RuntimeError):
    """The Codex process failed before producing an executable operation."""


class ProcessLike(Protocol):
    stdin: IO[str] | None
    stdout: IO[str] | None
    stderr: IO[str] | None

    def poll(self) -> int | None: ...

    def wait(self, timeout: float | None = None) -> int: ...

    def terminate(self) -> None: ...

    def kill(self) -> None: ...


ProcessFactory = Callable[[Sequence[str], str, Path], ProcessLike]


def _default_process_factory(
    command: Sequence[str],
    prompt: str,
    cwd: Path,
) -> ProcessLike:
    kwargs: dict[str, Any] = {}
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    process = subprocess.Popen(
        list(command),
        cwd=cwd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        encoding="utf-8",
        errors="replace",
        text=True,
        **kwargs,
    )
    if process.stdin is None:
        process.kill()
        raise OSError("Codex subprocess stdin was not created")
    process.stdin.write(prompt)
    process.stdin.close()
    return process


class _CodexEventMonitor:
    """Drain JSONL concurrently and retain no reasoning or tool-result bodies."""

    def __init__(self, process: ProcessLike) -> None:
        self.process = process
        self._lock = threading.RLock()
        self._tool_events: list[dict[str, Any]] = []
        self._event_counts: dict[str, int] = {}
        self._usage = _empty_usage()
        self._thread_id: str | None = None
        self._final_message: str | None = None
        self._stderr_sha256 = hashlib.sha256()
        self._stderr_byte_count = 0
        self._provider_errors: list[dict[str, Any]] = []
        self._stdout_thread = threading.Thread(
            target=self._read_stdout,
            name="chemworld-codex-jsonl",
            daemon=True,
        )
        self._stderr_thread = threading.Thread(
            target=self._read_stderr,
            name="chemworld-codex-stderr",
            daemon=True,
        )
        self._stdout_thread.start()
        self._stderr_thread.start()

    def alive(self) -> bool:
        return self.process.poll() is None

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "thread_id": self._thread_id,
                "usage": dict(self._usage),
                "event_counts": dict(self._event_counts),
                "tool_events": deepcopy(self._tool_events),
                "stderr_byte_count": self._stderr_byte_count,
                "stderr_sha256": self._stderr_sha256.hexdigest(),
                "provider_errors": deepcopy(self._provider_errors),
            }

    def wait(self, timeout_s: float) -> dict[str, Any]:
        try:
            return_code = self.process.wait(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            self.process.terminate()
            try:
                return_code = self.process.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                self.process.kill()
                return_code = self.process.wait(timeout=5.0)
            status = "timeout"
        else:
            status = "completed" if return_code == 0 else "failed"
        self._stdout_thread.join(timeout=5.0)
        self._stderr_thread.join(timeout=5.0)
        snapshot = self.snapshot()
        final_payload: dict[str, Any] | None = None
        with self._lock:
            message = self._final_message
        if message is not None:
            try:
                candidate = json.loads(message)
            except json.JSONDecodeError:
                candidate = None
            if isinstance(candidate, dict):
                final_payload = candidate
        return {
            **snapshot,
            "status": status,
            "return_code": int(return_code),
            "final_payload": final_payload,
        }

    def stop(self) -> None:
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5.0)
        self._stdout_thread.join(timeout=2.0)
        self._stderr_thread.join(timeout=2.0)

    def _read_stdout(self) -> None:
        stream = self.process.stdout
        if stream is None:
            return
        for line in stream:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict):
                continue
            self._consume_event(event)

    def _read_stderr(self) -> None:
        stream = self.process.stderr
        if stream is None:
            return
        for chunk in iter(lambda: stream.read(4096), ""):
            data = chunk.encode("utf-8", errors="replace")
            with self._lock:
                self._stderr_byte_count += len(data)
                self._stderr_sha256.update(data)

    def _consume_event(self, event: Mapping[str, Any]) -> None:
        event_type = str(event.get("type", "unknown"))
        with self._lock:
            self._event_counts[event_type] = self._event_counts.get(event_type, 0) + 1
            if event_type == "error":
                self._record_provider_error(event.get("message"))
            elif event_type == "turn.failed":
                error = event.get("error")
                if isinstance(error, Mapping):
                    self._record_provider_error(error.get("message"))
            if event_type == "thread.started":
                value = event.get("thread_id")
                if isinstance(value, str):
                    self._thread_id = value
            if event_type == "turn.completed" and isinstance(event.get("usage"), Mapping):
                self._usage = _normalize_usage(event["usage"])
            if event_type != "item.completed" or not isinstance(event.get("item"), Mapping):
                return
            item = event["item"]
            item_type = item.get("type")
            if item_type == "agent_message" and isinstance(item.get("text"), str):
                self._final_message = str(item["text"])
            elif item_type == "command_execution":
                self._tool_events.append(_sanitize_command_event(item))
            elif item_type == "file_change":
                self._tool_events.append(_sanitize_file_change_event(item))
            elif isinstance(item_type, str) and (
                "mcp" in item_type or item_type == "dynamic_tool_call"
            ):
                self._tool_events.append(_sanitize_mcp_tool_event(item))
            elif item_type == "reasoning":
                self._event_counts["reasoning_body_discarded"] = (
                    self._event_counts.get("reasoning_body_discarded", 0) + 1
                )

    def _record_provider_error(self, message: Any) -> None:
        """Retain only bounded metadata for provider errors, never their body."""

        if not isinstance(message, str):
            return
        encoded = message.encode("utf-8", errors="replace")
        entry = {
            "byte_count": len(encoded),
            "sha256": hashlib.sha256(encoded).hexdigest(),
        }
        if entry not in self._provider_errors:
            self._provider_errors.append(entry)


class InteractiveCodexExperimentAgent(BaseAgent):
    """Keep one native Codex context alive for every complete experiment."""

    name = "interactive_codex_experiment"

    def __init__(
        self,
        *,
        workspace: str | Path,
        role_id: str,
        model: str = "gpt-5.6-sol",
        reasoning_effort: str = "medium",
        model_provider: str = HTTPS_PROVIDER_ID,
        model_provider_name: str = "OpenAI",
        model_provider_base_url: str | None = None,
        model_provider_env_key: str | None = None,
        model_provider_wire_api: str = "responses",
        codex_executable: str | None = None,
        process_factory: ProcessFactory | None = None,
        request_timeout_s: float = 600.0,
        finalization_timeout_s: float = DEFAULT_FINALIZATION_TIMEOUT_S,
        pre_action_restart_limit: int = 1,
        max_initial_prompt_bytes: int = 65_536,
        max_tool_output_bytes: int = 32_768,
        history_event_limit: int = 64,
        history_byte_limit: int = 131_072,
    ) -> None:
        if model not in SUPPORTED_MODELS:
            raise ValueError(f"unsupported Codex model: {model}")
        if reasoning_effort not in {"low", "medium", "high", "xhigh", "max"}:
            raise ValueError("unsupported Codex reasoning effort")
        if not model_provider or not model_provider_name:
            raise ValueError("model provider id and name must be non-empty")
        if model_provider_wire_api != "responses":
            raise ValueError("interactive Codex runner currently requires wire_api=responses")
        if request_timeout_s <= 0 or finalization_timeout_s <= 0:
            raise ValueError("timeouts must be positive")
        if pre_action_restart_limit < 0:
            raise ValueError("pre_action_restart_limit must be non-negative")
        if max_initial_prompt_bytes < 4_096:
            raise ValueError("max_initial_prompt_bytes must be at least 4096")
        self._process_factory: ProcessFactory
        if process_factory is None:
            executable = codex_executable or shutil.which("codex")
            if not executable:
                raise InteractiveCodexExperimentError(
                    "Codex CLI is not installed or not available on PATH"
                )
            self.codex_executable = str(executable)
            self._process_factory = _default_process_factory
        else:
            self.codex_executable = codex_executable or "codex"
            self._process_factory = process_factory
        self.role_id = role_id
        self.model = model
        self.reasoning_effort = reasoning_effort
        self.model_provider = str(model_provider)
        self.model_provider_name = str(model_provider_name)
        self.model_provider_base_url = (
            None if model_provider_base_url is None else str(model_provider_base_url)
        )
        self.model_provider_env_key = (
            None if model_provider_env_key is None else str(model_provider_env_key)
        )
        self.model_provider_wire_api = str(model_provider_wire_api)
        self.request_timeout_s = float(request_timeout_s)
        self.finalization_timeout_s = float(finalization_timeout_s)
        self.pre_action_restart_limit = int(pre_action_restart_limit)
        self.max_initial_prompt_bytes = int(max_initial_prompt_bytes)
        self.workspace = ExperimentCodexWorkspace(
            workspace,
            max_tool_output_bytes=max_tool_output_bytes,
            history_event_limit=history_event_limit,
            history_byte_limit=history_byte_limit,
        )
        self._mcp_server_path = Path(__file__).with_name("experiment_codex_mcp.py").resolve()
        self._source_project_root = Path(__file__).resolve().parents[3]
        self._mcp_server_sha256 = _file_sha256(self._mcp_server_path)

    def _verify_experiment_tool(self) -> None:
        """Fail closed if either active MCP source or legacy fallback changes."""

        if _file_sha256(self._mcp_server_path) != self._mcp_server_sha256:
            raise ExperimentCodexIPCError("host-owned MCP server changed during the run")
        self.workspace.verify_lab_tool()

    def reset(self, task_info: dict[str, Any], seed: int) -> None:
        super().reset(task_info, seed)
        self.workspace.initialize_fresh()
        material_manifest = self.workspace.publish_material_information(
            _material_information_payload(task_info)
        )
        self._material_manifest = material_manifest
        self._task_contract = _public_task_contract(task_info)
        self._task_contract_manifest = self.workspace.publish_task_contract(self._task_contract)
        self._session: dict[str, Any] | None = None
        self._sessions_started = 0
        self._sessions_completed = 0
        self._all_session_usage_complete = True
        self._pre_action_restarts = 0
        self._handled_request_ids: set[str] = set()
        self._pending_request: IPCRequest | None = None
        self._pending_outcome: dict[str, Any] | None = None
        self._last_decision: dict[str, Any] | None = None
        self._last_context_remaining = 0
        self._global_runner_action_count = 0
        self._experiment_action_count = 0
        self._cumulative_usage = _empty_usage()
        self._session_receipts: list[dict[str, Any]] = []
        self._completed_tool_events: list[dict[str, Any]] = []
        self._last_agent_snapshot = self.workspace.snapshot_agent_files()
        self._session_temp_directories: list[tempfile.TemporaryDirectory[str]] = []

    def act(self, history: list[HistoryRecord]) -> dict[str, Any]:
        del history
        raise RuntimeError(
            "InteractiveCodexExperimentAgent requires the official public-view runner"
        )

    def act_with_public_view(
        self,
        context: AgentDecisionContext,
        public_view: dict[str, Any],
    ) -> dict[str, Any]:
        self._verify_experiment_tool()
        artifact = self._publish_latest_artifact(public_view)
        current_packet = _bounded_current_packet(
            context,
            public_view,
            artifact=artifact,
        )
        current_manifest = self.workspace.publish_current(current_packet)
        if self._session is None:
            self._start_session(current_packet)
        elif self._pending_request is not None and self._pending_outcome is not None:
            response = {
                **self._pending_outcome,
                "next_state": current_packet,
            }
            self.workspace.write_response(
                session_id=self._pending_request.session_id,
                request_id=self._pending_request.request_id,
                response=response,
            )
            self._pending_request = None
            self._pending_outcome = None

        self._last_context_remaining = context.remaining_operations
        request = self._wait_for_next_request(current_packet)
        try:
            self._verify_experiment_tool()
            self.workspace.verify_file(
                relative_path=str(self._material_manifest["relative_path"]),
                expected_sha256=str(self._material_manifest["sha256"]),
            )
            self.workspace.verify_file(
                relative_path=str(self._task_contract_manifest["relative_path"]),
                expected_sha256=str(self._task_contract_manifest["sha256"]),
            )
            self.workspace.verify_file(
                relative_path="public/current.json",
                expected_sha256=str(current_manifest["sha256"]),
            )
        except ExperimentCodexIPCError as error:
            self.close()
            raise InteractiveCodexExperimentError(
                "Codex modified a host-owned bridge/reference file; "
                "no environment action was emitted"
            ) from error
        self._handled_request_ids.add(request.request_id)
        if self._session is None:
            raise InteractiveCodexExperimentError("Codex session ended before action acceptance")
        self._session["accepted_action_count"] = int(self._session["accepted_action_count"]) + 1
        self._pending_request = request
        self._experiment_action_count += 1
        self._global_runner_action_count += 1
        self._last_decision = {
            "schema_version": INTERACTIVE_CODEX_EXPERIMENT_VERSION,
            "status": "codex_lab_tool_action",
            "action": to_builtin(request.action),
            "session_id": request.session_id,
            "request_id": request.request_id,
            "expected_step": request.expected_step,
            "action_payload_sha256": request.payload_sha256,
            "current_public_state": current_manifest,
            "authoritative_ledger_in_workspace": False,
            "decision_audit_status": "not_provided",
        }
        return dict(request.action)

    def update(
        self,
        action: dict[str, Any],
        observation: dict[str, float | None],
        reward: float,
        info: dict[str, Any],
    ) -> None:
        if self._pending_request is None:
            raise InteractiveCodexExperimentError(
                "runner returned an outcome without a pending Codex request"
            )
        if to_builtin(action) != self._pending_request.action:
            raise InteractiveCodexExperimentError(
                "runner action differs from the accepted Codex request"
            )
        self._verify_experiment_tool()
        event_id = f"runner-operation-{self._global_runner_action_count:04d}"
        artifact = self._publish_outcome_artifact(
            event_id=event_id,
            action=action,
            info=info,
        )
        outcome = _compact_outcome(
            event_id=event_id,
            action=action,
            observation=observation,
            reward=reward,
            info=info,
            artifact=artifact,
        )
        self.workspace.append_public_history(
            {
                "schema_version": INTERACTIVE_CODEX_EXPERIMENT_VERSION,
                **outcome,
            }
        )
        self.workspace.update_expected_step(
            session_id=self._pending_request.session_id,
            expected_step=self._experiment_action_count + 1,
        )
        successful_final_assay = bool(
            action.get("operation") == "measure"
            and action.get("instrument") == "final_assay"
            and info.get("transaction_status") == "committed"
            and info.get("leaderboard_score") is not None
        )
        ended = bool(info.get("experiment_ended", False) or successful_final_assay)
        batch_discarded = bool(info.get("batch_discarded", False))
        experiment_completed = bool(
            info.get("experiment_completed", not batch_discarded)
        )
        budget_exhausted = self._last_context_remaining <= 1 and not ended
        self._pending_outcome = {
            "ok": True,
            "schema_version": EXPERIMENT_CODEX_IPC_VERSION,
            **outcome,
            "experiment_ended": ended,
            "experiment_completed": experiment_completed,
            "batch_discarded": batch_discarded,
            "budget_exhausted": budget_exhausted,
        }
        if self._last_decision is not None:
            self._last_decision["outcome"] = deepcopy(self._pending_outcome)

        before = self._last_agent_snapshot
        after = self.workspace.snapshot_agent_files()
        memory_diff = diff_agent_snapshots(before, after)
        self._last_agent_snapshot = after
        if self._last_decision is not None:
            self._last_decision["agent_workspace_changes"] = memory_diff

        if ended or budget_exhausted:
            self.workspace.write_response(
                session_id=self._pending_request.session_id,
                request_id=self._pending_request.request_id,
                response={**self._pending_outcome, "next_state": None},
            )
            self._finalize_session(
                terminal_reason=(
                    "batch_discarded"
                    if batch_discarded
                    else "experiment_complete"
                    if ended
                    else "budget_exhausted"
                )
            )
            self._pending_request = None
            self._pending_outcome = None
            self._experiment_action_count = 0

    def decision_audit(self) -> None:
        """The IPC action is auditable, but no synthetic scientific rationale is added."""

        return None

    def agent_trace(self) -> list[dict[str, Any]]:
        if self._last_decision is None:
            return []
        trace = deepcopy(self._last_decision)
        if self._session is not None:
            monitor = self._session["monitor"]
            if isinstance(monitor, _CodexEventMonitor):
                snapshot = monitor.snapshot()
                trace["live_session_audit"] = {
                    "event_counts": snapshot["event_counts"],
                    "tool_event_count": len(snapshot["tool_events"]),
                    "usage_finalized": False,
                }
                trace["artifact_access_count"] = len(
                    self.workspace.artifact_access_audit(str(self._session["session_id"]))
                )
        return [to_builtin(trace)]

    def interaction_capabilities(self) -> InteractionCapabilities:
        return InteractionCapabilities(
            decision_scope="operation",
            consumes_intermediate_observations=True,
            consumes_spectra=True,
            adapts_within_experiment=True,
            adapts_across_experiments=True,
            emits_structured_decision_audit=False,
        )

    def manifest(self) -> dict[str, Any]:
        payload = super().manifest()
        payload.update(
            {
                "role_id": self.role_id,
                "requires_online_model": True,
                "provider": self.model_provider_name,
                "provider_id": self.model_provider,
                "provider_base_url": self.model_provider_base_url,
                "provider_env_key": self.model_provider_env_key,
                "provider_model": self.model,
                "reasoning_effort": self.reasoning_effort,
                "interaction_version": INTERACTIVE_CODEX_EXPERIMENT_VERSION,
                "one_codex_exec_per_complete_experiment": True,
                "codex_exec_ephemeral": True,
                "experiment_tool_transport": "host_owned_stdio_mcp",
                "mcp_server": {
                    "name": "chemworld_lab",
                    "version": MCP_SERVER_VERSION,
                    "required": True,
                    "enabled_tools": list(SUPPORTED_TOOLS),
                    "source_sha256": self._mcp_server_sha256,
                    "model_generated_shell_required": False,
                },
                "automatic_action_repair": False,
                "automatic_closeout": False,
                "authoritative_trajectory_in_workspace": False,
                "agent_workspace_optional": True,
                "forced_notebook": False,
                "material_information_reference": deepcopy(self._material_manifest),
                "task_contract_reference": deepcopy(self._task_contract_manifest),
                "workspace": self.workspace.manifest(),
                "usage_accounting_granularity": "complete_codex_experiment_turn",
                "provider_session_count": self._sessions_started,
                "logical_codex_turn_count": self._sessions_started,
                "backend_model_response_count": None,
                "backend_model_response_accounting_complete": False,
                "input_token_accounting_semantics": (
                    "cumulative_input_across_the_complete_codex_turn"
                ),
        }
        )
        return payload

    def method_resource_usage(self) -> dict[str, Any]:
        active = self._session is not None
        provider_usage_complete = bool(not active and self._all_session_usage_complete)
        usage = dict(self._cumulative_usage)
        return {
            "schema_version": "chemworld-method-resource-usage-0.1",
            "accounting_complete": False,
            "provider_usage_pending": active,
            "in_flight_model_call_count": 1 if active else 0,
            "provider_usage_accounting_complete": provider_usage_complete,
            "provider_call_accounting_complete": True,
            "provider_token_accounting_complete": provider_usage_complete,
            "provider_cache_accounting_complete": provider_usage_complete,
            "monetary_accounting_complete": False,
            "usage_source": (
                "active_codex_turn_usage_pending"
                if active
                else (
                    "codex_cli_completed_experiment_turns"
                    if provider_usage_complete
                    else "codex_cli_incomplete_interrupted_turns"
                )
            ),
            "model_call_count": self._sessions_started,
            "provider_session_count": self._sessions_started,
            "logical_codex_turn_count": self._sessions_started,
            "backend_model_response_count": None,
            "backend_model_response_accounting_complete": False,
            "input_token_count": usage["prompt_tokens"],
            "cached_input_token_count": usage["prompt_cache_hit_tokens"],
            "uncached_input_token_count": usage["prompt_cache_miss_tokens"],
            "input_cache_hit_ratio": (
                usage["prompt_cache_hit_tokens"] / usage["prompt_tokens"]
                if usage["prompt_tokens"]
                else 0.0
            ),
            "output_token_count": usage["completion_tokens"],
            "monetary_cost_usd": 0.0,
            "training_environment_step_count": 0,
            "cpu_time_s": 0.0,
            "gpu_time_s": 0.0,
            "model_provenance": {
                "provider": self.model_provider_name,
                "provider_id": self.model_provider,
                "provider_base_url": self.model_provider_base_url,
                "model_id": self.model,
                "model_snapshot_or_access_date": MODEL_ACCESS_DATE,
                "prompt_hash": _system_prompt_hash(),
                "request_parameters": {
                    "reasoning_effort": self.reasoning_effort,
                    "one_turn_per_experiment": True,
                    "workspace_tools": True,
                    "experiment_tool_transport": "host_owned_stdio_mcp",
                    "forced_notebook": False,
                },
                "tokenizer_or_provider_usage_source": "codex exec turn.completed",
                "input_token_accounting_semantics": (
                    "cumulative_input_across_the_complete_codex_turn; cache hits are "
                    "reused input tokens, not generated output"
                ),
                "pricing": {
                    "accounting_complete": False,
                    "model_source": MODEL_SOURCE,
                    "auth_source": AUTH_SOURCE,
                    "pricing_unavailable_reason": (
                        "ChatGPT subscription usage has no attributable per-run USD price"
                    ),
                },
                "private_reasoning_retained": False,
                "completed_session_count": self._sessions_completed,
            },
        }

    def provider_receipts(self) -> list[dict[str, Any]]:
        return deepcopy(self._session_receipts)

    def close(self) -> None:
        """Stop an unfinished process; the official runner may call this on interruption."""

        if self._session is not None:
            self._record_interrupted_session(reason="agent_closed")

    def _start_session(self, current_packet: Mapping[str, Any]) -> None:
        session_id = f"experiment-{self._sessions_started + 1:04d}-{uuid4().hex[:12]}"
        self.workspace.start_session(
            session_id=session_id,
            expected_step=1,
            response_timeout_s=self.request_timeout_s,
        )
        temporary = tempfile.TemporaryDirectory(prefix="chemworld-interactive-codex-")
        self._session_temp_directories.append(temporary)
        temp_root = Path(temporary.name)
        instructions_path = temp_root / "instructions.md"
        schema_path = temp_root / "final-schema.json"
        instructions_path.write_text(_SYSTEM_PROMPT, encoding="utf-8")
        schema_path.write_text(
            json.dumps(_FINAL_OUTPUT_SCHEMA, sort_keys=True),
            encoding="utf-8",
        )
        prompt = _initial_prompt(
            task_contract=self._task_contract,
            task_contract_manifest=self._task_contract_manifest,
            current_packet=current_packet,
            material_manifest=self._material_manifest,
        )
        if len(prompt.encode("utf-8")) > self.max_initial_prompt_bytes:
            raise InteractiveCodexExperimentError(
                "initial experiment prompt exceeds its hard byte cap"
            )
        command = self._command(
            instructions_path=instructions_path,
            schema_path=schema_path,
        )
        process = self._process_factory(
            command,
            prompt,
            self.workspace.agent_directory,
        )
        monitor = _CodexEventMonitor(process)
        self._sessions_started += 1
        self._session = {
            "session_id": session_id,
            "monitor": monitor,
            "temp": temporary,
            "accepted_action_count": 0,
            "prompt_byte_count": len(prompt.encode("utf-8")),
            "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        }

    def _wait_for_next_request(
        self,
        current_packet: Mapping[str, Any],
    ) -> IPCRequest:
        while True:
            if self._session is None:
                raise InteractiveCodexExperimentError("Codex session is not active")
            session_id = str(self._session["session_id"])
            monitor = self._session["monitor"]
            if not isinstance(monitor, _CodexEventMonitor):
                raise TypeError("invalid Codex monitor")
            try:
                request = self.workspace.wait_for_request(
                    session_id=session_id,
                    expected_step=self._experiment_action_count + 1,
                    timeout_s=self.request_timeout_s,
                    process_alive=monitor.alive,
                    handled_request_ids=self._handled_request_ids,
                )
            except (ExperimentCodexIPCError, TimeoutError) as error:
                accepted = int(self._session.get("accepted_action_count", 0))
                can_restart = (
                    accepted == 0 and self._pre_action_restarts < self.pre_action_restart_limit
                )
                self._record_interrupted_session(
                    reason=type(error).__name__,
                )
                if can_restart:
                    self._pre_action_restarts += 1
                    self._start_session(current_packet)
                    continue
                raise InteractiveCodexExperimentError(
                    "Codex failed before the next executable operation; "
                    "no fallback action was emitted"
                ) from error
            return request

    def _finalize_session(self, *, terminal_reason: str) -> None:
        if self._session is None:
            return
        monitor = self._session["monitor"]
        if not isinstance(monitor, _CodexEventMonitor):
            raise TypeError("invalid Codex monitor")
        result = monitor.wait(self.finalization_timeout_s)
        integrity_error: ExperimentCodexIPCError | None = None
        try:
            self._verify_experiment_tool()
        except ExperimentCodexIPCError as error:
            integrity_error = error
        usage = result.get("usage")
        normalized_usage = usage if isinstance(usage, dict) else _empty_usage()
        _merge_usage(self._cumulative_usage, normalized_usage)
        tool_events = result.get("tool_events")
        if isinstance(tool_events, list):
            self._completed_tool_events.extend(
                item for item in tool_events if isinstance(item, dict)
            )
        session_id = str(self._session["session_id"])
        mcp_tool_calls = self.workspace.mcp_tool_call_audit(session_id)
        receipt_tool_events = (
            [item for item in tool_events if isinstance(item, dict)]
            if isinstance(tool_events, list)
            else []
        )
        if mcp_tool_calls and not any(
            event.get("event_type") == "mcp_tool_call"
            for event in receipt_tool_events
        ):
            receipt_tool_events.extend(_host_mcp_audit_events(mcp_tool_calls))
        final_payload = result.get("final_payload")
        final_valid = _valid_final_payload(final_payload)
        usage_complete = _usage_complete(normalized_usage)
        self._all_session_usage_complete = self._all_session_usage_complete and usage_complete
        receipt = {
            "schema_version": "chemworld-interactive-codex-session-receipt-0.1",
            "session_id": self._session["session_id"],
            "thread_id": result.get("thread_id"),
            "status": result.get("status"),
            "return_code": result.get("return_code"),
            "terminal_reason": terminal_reason,
            "model_id": self.model,
            "reasoning_effort": self.reasoning_effort,
            "usage": normalized_usage,
            "usage_complete": usage_complete,
            "prompt_byte_count": self._session["prompt_byte_count"],
            "prompt_sha256": self._session["prompt_sha256"],
            "tool_events": receipt_tool_events,
            "event_counts": result.get("event_counts", {}),
            "provider_errors": result.get("provider_errors", []),
            "final_payload_valid": final_valid,
            "final_payload_status": (
                final_payload.get("status")
                if final_valid and isinstance(final_payload, dict)
                else None
            ),
            "final_payload_summary": (
                str(final_payload["summary"])
                if final_valid and isinstance(final_payload, dict)
                else None
            ),
            "stderr_byte_count": result.get("stderr_byte_count", 0),
            "stderr_sha256": result.get("stderr_sha256"),
            "artifact_access": self.workspace.artifact_access_audit(
                str(self._session["session_id"])
            ),
            "mcp_tool_calls": mcp_tool_calls,
            "experiment_tool_transport": "host_owned_stdio_mcp",
            "mcp_tool_integrity_verified_after_session": integrity_error is None,
            "experiment_tool_integrity_verified_after_session": integrity_error is None,
            "lab_tool_integrity_verified_after_session": integrity_error is None,
            "private_reasoning_retained": False,
        }
        self._session_receipts.append(to_builtin(receipt))
        self._sessions_completed += 1
        if self._last_decision is not None:
            self._last_decision["completed_session_receipt"] = to_builtin(receipt)
        self._retire_active_session()
        self._session = None
        if integrity_error is not None:
            raise InteractiveCodexExperimentError(
                "the experiment tool bridge failed its post-session integrity check"
            ) from integrity_error

    def _record_interrupted_session(self, *, reason: str) -> None:
        """Retain an attempt receipt even when no environment action was emitted."""

        if self._session is None:
            return
        monitor = self._session.get("monitor")
        if not isinstance(monitor, _CodexEventMonitor):
            self._retire_active_session()
            self._session = None
            return
        monitor.stop()
        snapshot = monitor.snapshot()
        try:
            self._verify_experiment_tool()
        except ExperimentCodexIPCError:
            experiment_tool_integrity_verified = False
        else:
            experiment_tool_integrity_verified = True
        usage = snapshot.get("usage")
        normalized_usage = usage if isinstance(usage, dict) else _empty_usage()
        _merge_usage(self._cumulative_usage, normalized_usage)
        usage_complete = _usage_complete(normalized_usage)
        self._all_session_usage_complete = self._all_session_usage_complete and usage_complete
        tool_events = snapshot.get("tool_events")
        session_id = str(self._session["session_id"])
        mcp_tool_calls = self.workspace.mcp_tool_call_audit(session_id)
        receipt_tool_events = (
            [item for item in tool_events if isinstance(item, dict)]
            if isinstance(tool_events, list)
            else []
        )
        if mcp_tool_calls and not any(
            event.get("event_type") == "mcp_tool_call"
            for event in receipt_tool_events
        ):
            receipt_tool_events.extend(_host_mcp_audit_events(mcp_tool_calls))
        receipt = {
            "schema_version": "chemworld-interactive-codex-session-receipt-0.1",
            "session_id": self._session["session_id"],
            "thread_id": snapshot.get("thread_id"),
            "status": "interrupted_before_next_action",
            "failure_type": reason,
            "model_id": self.model,
            "reasoning_effort": self.reasoning_effort,
            "usage": normalized_usage,
            "usage_complete": usage_complete,
            "prompt_byte_count": self._session["prompt_byte_count"],
            "prompt_sha256": self._session["prompt_sha256"],
            "tool_events": receipt_tool_events,
            "event_counts": snapshot.get("event_counts", {}),
            "provider_errors": snapshot.get("provider_errors", []),
            "stderr_byte_count": snapshot.get("stderr_byte_count", 0),
            "stderr_sha256": snapshot.get("stderr_sha256"),
            "mcp_tool_calls": mcp_tool_calls,
            "experiment_tool_transport": "host_owned_stdio_mcp",
            "mcp_tool_integrity_verified_after_session": (
                experiment_tool_integrity_verified
            ),
            "experiment_tool_integrity_verified_after_session": (
                experiment_tool_integrity_verified
            ),
            "lab_tool_integrity_verified_after_session": (
                experiment_tool_integrity_verified
            ),
            "private_reasoning_retained": False,
        }
        self._session_receipts.append(to_builtin(receipt))
        self._sessions_completed += 1
        self._retire_active_session()
        self._session = None

    def _retire_active_session(self) -> None:
        """Drop protocol files and temporary prompts after retaining their audit."""

        if self._session is None:
            return
        session_id = str(self._session["session_id"])
        temporary = self._session.get("temp")
        if isinstance(temporary, tempfile.TemporaryDirectory):
            temporary.cleanup()
            if temporary in self._session_temp_directories:
                self._session_temp_directories.remove(temporary)
        self.workspace.retire_session(session_id)

    def _publish_outcome_artifact(
        self,
        *,
        event_id: str,
        action: Mapping[str, Any],
        info: Mapping[str, Any],
    ) -> dict[str, Any] | None:
        if action.get("operation") != "measure":
            return None
        raw = info.get("raw_signal")
        if not isinstance(raw, Mapping) or not raw:
            return None
        artifact_id = f"characterization-{event_id}"
        return self.workspace.publish_artifact(
            artifact_id=artifact_id,
            payload={
                "schema_version": "chemworld-public-characterization-artifact-0.1",
                "event_id": event_id,
                "instrument": action.get("instrument"),
                "raw_signal": to_builtin(raw),
            },
        )

    def _publish_latest_artifact(
        self,
        public_view: Mapping[str, Any],
    ) -> dict[str, Any] | None:
        if self._pending_outcome is None:
            return None
        existing = self._pending_outcome.get("artifact")
        if isinstance(existing, Mapping):
            return deepcopy(dict(existing))
        action = self._pending_outcome.get("action")
        if not isinstance(action, Mapping) or action.get("operation") != "measure":
            return None
        tool = public_view.get("tool_json")
        raw = tool.get("raw_signal") if isinstance(tool, Mapping) else None
        if not isinstance(raw, Mapping) or not raw:
            return None
        event_id = str(self._pending_outcome["event_id"])
        artifact_id = f"characterization-{event_id}"
        return self.workspace.publish_artifact(
            artifact_id=artifact_id,
            payload={
                "schema_version": "chemworld-public-characterization-artifact-0.1",
                "event_id": event_id,
                "instrument": action.get("instrument"),
                "raw_signal": to_builtin(raw),
            },
        )

    def _command(self, *, instructions_path: Path, schema_path: Path) -> list[str]:
        return [
            self.codex_executable,
            "exec",
            "--json",
            "--ephemeral",
            "--ignore-user-config",
            "--ignore-rules",
            "--skip-git-repo-check",
            "--output-schema",
            str(schema_path),
            "--disable",
            "apps",
            "--disable",
            "multi_agent",
            "--disable",
            "plugins",
            "--sandbox",
            "workspace-write",
            "-c",
            'approval_policy="never"',
            "-c",
            'web_search="disabled"',
            "-c",
            f"mcp_servers.chemworld_lab.command={json.dumps(sys.executable)}",
            "-c",
            (
                "mcp_servers.chemworld_lab.args="
                + json.dumps(
                    [
                        "-m",
                        "chemworld.agents.experiment_codex_mcp",
                        "--workspace",
                        str(self.workspace.root),
                    ]
                )
            ),
            "-c",
            (
                "mcp_servers.chemworld_lab.cwd="
                + json.dumps(str(self._source_project_root))
            ),
            "-c",
            "mcp_servers.chemworld_lab.required=true",
            "-c",
            "mcp_servers.chemworld_lab.enabled=true",
            "-c",
            (
                "mcp_servers.chemworld_lab.enabled_tools="
                + json.dumps(list(SUPPORTED_TOOLS))
            ),
            "-c",
            'mcp_servers.chemworld_lab.default_tools_approval_mode="approve"',
            "-c",
            'mcp_servers.chemworld_lab.tools.step.approval_mode="approve"',
            "-c",
            "mcp_servers.chemworld_lab.startup_timeout_sec=30",
            "-c",
            (
                "mcp_servers.chemworld_lab.tool_timeout_sec="
                + str(int(self.request_timeout_s + 31.0))
            ),
            "-c",
            f'model_provider="{self.model_provider}"',
            *self._model_provider_config_overrides(),
            "-c",
            f'model_reasoning_effort="{self.reasoning_effort}"',
            "-c",
            f"model_instructions_file={json.dumps(instructions_path.as_posix())}",
            "-m",
            self.model,
            "-C",
            str(self.workspace.agent_directory),
        ]

    def _model_provider_config_overrides(self) -> list[str]:
        """Render bounded Codex CLI provider overrides without exposing secrets."""

        if self.model_provider == HTTPS_PROVIDER_ID:
            config = (
                '{name="OpenAI",wire_api="responses",requires_openai_auth=true,'
                "supports_websockets=false}"
            )
            return ["-c", f"model_providers.{self.model_provider}={config}"]
        else:
            fields = [
                f"model_providers.{self.model_provider}.name={json.dumps(self.model_provider_name)}",
                f"model_providers.{self.model_provider}.wire_api={json.dumps(self.model_provider_wire_api)}",
            ]
            if self.model_provider_base_url:
                fields.append(
                    f"model_providers.{self.model_provider}.base_url={json.dumps(self.model_provider_base_url)}"
                )
            if self.model_provider_env_key:
                fields.append(
                    f"model_providers.{self.model_provider}.env_key={json.dumps(self.model_provider_env_key)}"
                )
            fields.append(
                f"model_providers.{self.model_provider}.supports_websockets=false"
            )
            rendered: list[str] = []
            for field in fields:
                rendered.extend(["-c", field])
            return rendered


def _initial_prompt(
    *,
    task_contract: Mapping[str, Any],
    task_contract_manifest: Mapping[str, Any],
    current_packet: Mapping[str, Any],
    material_manifest: Mapping[str, Any],
) -> str:
    payload = {
        "schema_version": INTERACTIVE_CODEX_EXPERIMENT_VERSION,
        "instruction": (
            "Complete one experiment autonomously and optimize the declared leaderboard "
            "score under the scoring contract's component weights, gates, safety, and "
            "resource limits. Current state is authoritative; submit every operation "
            "through chemworld_lab.step. No host closeout is available."
        ),
        "task": to_builtin(dict(task_contract)),
        "task_contract_reference": {
            "contents_in_prompt": True,
            **to_builtin(dict(task_contract_manifest)),
            "relative_path": "../reference/task_contract.json",
        },
        "material_information": {
            "contents_in_prompt": False,
            **to_builtin(dict(material_manifest)),
            "relative_path": "../reference/material_information.json",
        },
        "initial_public_state": to_builtin(dict(current_packet)),
        "workspace": {
            "writable_root": "agent/ (current working directory; optional memory)",
            "transport": "host-owned STDIO MCP; no shell command is required",
            "mcp_server": "chemworld_lab (required, bounded, host-owned)",
            "material_reference": "chemworld_lab.material_information",
            "task_contract_reference": "../reference/task_contract.json",
            "public_history": "bounded non-authoritative cache",
            "authoritative_trajectory_available": False,
        },
        "mcp_step_example": {
            "expected_step": 1,
            "action": {"operation": "one currently legal operation"},
            "submit_with": "chemworld_lab.step",
        },
    }
    return _canonical_json(payload)


def _bounded_current_packet(
    context: AgentDecisionContext,
    public_view: Mapping[str, Any],
    *,
    artifact: Mapping[str, Any] | None,
) -> dict[str, Any]:
    tool = public_view.get("tool_json")
    tool_view = tool if isinstance(tool, Mapping) else {}
    available = tool_view.get("available_actions")
    actions = (
        [
            _compact_legal_action(item)
            for item in available
            if isinstance(item, Mapping) and item.get("valid") is not False
        ]
        if isinstance(available, list)
        else []
    )
    state = context.to_dict()
    campaign = state.get("campaign_state")
    campaign_mapping = campaign if isinstance(campaign, Mapping) else {}
    tool_campaign = tool_view.get("campaign_state")
    tool_campaign_mapping = tool_campaign if isinstance(tool_campaign, Mapping) else {}
    resource_snapshot: Any = None
    for source in (campaign_mapping, tool_campaign_mapping, tool_view):
        for key in (
            "campaign_resources",
            "campaign_resource_state",
            "resource_state",
            "resource_ledger",
        ):
            candidate = source.get(key)
            if isinstance(candidate, Mapping):
                resource_snapshot = candidate
                break
        if resource_snapshot is not None:
            break
    compact_campaign = _compact_scalars(campaign_mapping)
    for key in ("completed_batches", "discarded_batches", "experiment_summaries"):
        if key in campaign_mapping:
            compact_campaign[key] = _compact_nested(campaign_mapping.get(key))
    return {
        "schema_version": INTERACTIVE_CODEX_EXPERIMENT_VERSION,
        "step": context.step,
        "stage": context.decision_stage,
        "remaining_operations": context.remaining_operations,
        "campaign_state": compact_campaign,
        "campaign_resources": _compact_nested(resource_snapshot),
        "visible_metrics": _compact_scalars(context.visible_metrics),
        "latest_measurement": summarize_measurement(context.latest_spectra),
        "characterization_artifact": to_builtin(artifact) if artifact else None,
        "active_constraint_flags": {
            str(key): to_builtin(value)
            for key, value in context.constraint_flags.items()
            if value not in (None, False, 0, "", [], {})
        },
        "uncertainty": _compact_scalars(context.uncertainty),
        "legal_actions": actions,
    }


def _compact_outcome(
    *,
    event_id: str,
    action: Mapping[str, Any],
    observation: Mapping[str, Any],
    reward: float,
    info: Mapping[str, Any],
    artifact: Mapping[str, Any] | None,
) -> dict[str, Any]:
    return {
        "event_id": event_id,
        "action": to_builtin(dict(action)),
        "transaction_status": info.get("transaction_status"),
        "operation_type": info.get("operation_type", action.get("operation")),
        "reward": float(reward),
        "observation": {
            str(key): to_builtin(value) for key, value in observation.items() if value is not None
        },
        "processed_estimate": _compact_nested(info.get("processed_estimate")),
        "observed_keys": to_builtin(info.get("observed_keys", [])),
        "constraint_flags": {
            str(key): to_builtin(value)
            for key, value in (
                info.get("constraint_flags", {}).items()
                if isinstance(info.get("constraint_flags"), Mapping)
                else ()
            )
            if value not in (None, False, 0, "", [], {})
        },
        "error_message": info.get("error_message"),
        "leaderboard_score": info.get("leaderboard_score"),
        "measurement_cost": info.get("measurement_cost"),
        "sample_consumed": info.get("sample_consumed"),
        "state_delta_summary": _compact_nested(info.get("state_delta_summary")),
        "artifact": to_builtin(artifact) if artifact else None,
    }


def _material_information_payload(task_info: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "chemworld-env-owned-material-information-reference-0.1",
        "material_information": to_builtin(task_info.get("material_information")),
        "material_catalog": to_builtin(task_info.get("material_catalog", {})),
    }


def _public_task_contract(task_info: Mapping[str, Any]) -> dict[str, Any]:
    keys = (
        "env_id",
        "task_id",
        "task_contract_hash",
        "composition",
        "task_goal",
        "objective",
        "description",
        "budget",
        "official_budget",
        "episode_mode",
        "contract_profile",
        "safety_limit",
        "success_metrics",
        "constraints",
        "termination_policy",
        "observation_policy",
        "measurement_policy",
        "observation_contract",
        "observation_contract_hash",
        "experiment_lifecycle",
        "autonomous_workflow",
        "electrochemical_workflow_mode",
        "allowed_operations",
        "allowed_instruments",
        "method_budget_contract",
        "campaign_resource_card",
        "campaign_resources",
        "scoring_contract",
        "scoring_contract_hash",
        "scoring_contract_id",
        "scoring_weights",
        "objective_weights",
        "submission_requirements",
    )
    contract = {
        "schema_version": "chemworld-public-interactive-task-contract-0.1",
        **{key: to_builtin(task_info[key]) for key in keys if key in task_info},
    }
    if not isinstance(contract.get("experiment_lifecycle"), Mapping):
        allowed_operations = {
            str(value) for value in task_info.get("allowed_operations", [])
        }
        allowed_instruments = {
            str(value) for value in task_info.get("allowed_instruments", [])
        }
        if "terminate" in allowed_operations and "final_assay" in allowed_instruments:
            method_budget = task_info.get("method_budget_contract")
            planned_experiments = (
                method_budget.get("complete_experiment_limit", 1)
                if isinstance(method_budget, Mapping)
                else 1
            )
            contract["experiment_lifecycle"] = {
                "schema_version": "chemworld-public-experiment-lifecycle-0.1",
                "planned_complete_experiments": int(planned_experiments),
                "explicit_terminate_required": True,
                "final_assay_required": True,
                "final_assay_after_terminate": True,
                "automatic_closeout": False,
            }
    return contract


def _compact_legal_action(item: Mapping[str, Any]) -> dict[str, Any]:
    compact = compact_action(item)
    schema = item.get("schema")
    fields = schema.get("fields") if isinstance(schema, Mapping) else None
    if not isinstance(fields, list):
        return compact
    for field in fields:
        if not isinstance(field, Mapping):
            continue
        name = field.get("field", field.get("name"))
        labels = field.get("choice_labels")
        if not isinstance(name, str) or not isinstance(labels, Mapping):
            continue
        target = compact.get(name)
        if isinstance(target, dict):
            target["choice_labels"] = {str(key): str(value) for key, value in labels.items()}
    return compact


def _compact_scalars(value: Any, *, limit: int = 32) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    result: dict[str, Any] = {}
    for key in sorted(value):
        item = value[key]
        if item is None or isinstance(item, bool | int | float):
            result[str(key)] = to_builtin(item)
        elif isinstance(item, str) and len(item) <= 256:
            result[str(key)] = item
        if len(result) >= limit:
            break
    return result


def _compact_nested(value: Any, *, depth: int = 0) -> Any:
    if depth > 4:
        return None
    if value is None or isinstance(value, bool | int | float):
        return to_builtin(value)
    if isinstance(value, str):
        return value[:512]
    if isinstance(value, Mapping):
        return {
            str(key): compact
            for key, item in list(value.items())[:32]
            if (compact := _compact_nested(item, depth=depth + 1)) is not None
        }
    if isinstance(value, list | tuple) and len(value) <= 16:
        return [
            compact
            for item in value
            if (compact := _compact_nested(item, depth=depth + 1)) is not None
        ]
    return None


def _sanitize_command_event(item: Mapping[str, Any]) -> dict[str, Any]:
    command = str(item.get("command", ""))
    output = str(item.get("aggregated_output", ""))
    lower = command.lower()
    if "lab_tool.py step" in lower:
        classification = "lab_step"
    elif "lab_tool.py inspect" in lower:
        classification = "artifact_inspect"
    elif "lab_tool.py history" in lower:
        classification = "history_read"
    elif "lab_tool.py status" in lower:
        classification = "status_read"
    elif any(marker in lower for marker in ("get-content", "type ", " cat ")):
        classification = "file_read"
    elif any(marker in lower for marker in ("set-content", "out-file", "apply_patch")):
        classification = "file_write"
    else:
        classification = "other"
    paths = sorted(
        {
            match.replace("\\", "/")
            for match in re.findall(
                r"(?:agent|public|reference)/[A-Za-z0-9_.\-/]+",
                command.replace("\\", "/"),
            )
        }
    )
    data = output.encode("utf-8", errors="replace")
    return {
        "event_type": "command_execution",
        "classification": classification,
        "command_sha256": hashlib.sha256(command.encode("utf-8")).hexdigest(),
        "referenced_relative_paths": paths[:16],
        "output_byte_count": len(data),
        "output_line_count": len(output.splitlines()),
        "output_sha256": hashlib.sha256(data).hexdigest(),
        "exit_code": item.get("exit_code"),
        "status": item.get("status"),
        "command_body_retained": False,
        "output_body_retained": False,
    }


def _sanitize_file_change_event(item: Mapping[str, Any]) -> dict[str, Any]:
    changes: list[dict[str, Any]] = []
    raw = item.get("changes")
    for change in raw if isinstance(raw, list) else ():
        if not isinstance(change, Mapping):
            continue
        path = str(change.get("path", "")).replace("\\", "/")
        changes.append({"path": path, "kind": change.get("kind")})
    return {
        "event_type": "file_change",
        "changes": changes[:64],
        "content_retained": False,
    }


def _mcp_tool_classification(tool_name: str) -> str:
    return {
        "step": "lab_step",
        "status": "status_read",
        "history": "history_read",
        "inspect_artifact": "artifact_inspect",
        "material_information": "material_information_read",
    }.get(tool_name, "other")


def _sanitize_mcp_tool_event(item: Mapping[str, Any]) -> dict[str, Any]:
    raw_tool = item.get("tool") or item.get("name") or item.get("tool_name") or ""
    tool_name = str(raw_tool).rsplit("__", maxsplit=1)[-1]
    arguments = item.get("arguments") or item.get("input") or {}
    result = item.get("result") or item.get("output") or {}
    return {
        "event_type": "mcp_tool_call",
        "classification": _mcp_tool_classification(tool_name),
        "server": "chemworld_lab",
        "tool": tool_name,
        "arguments_sha256": hashlib.sha256(_canonical_json(arguments).encode("utf-8")).hexdigest(),
        "result_sha256": hashlib.sha256(_canonical_json(result).encode("utf-8")).hexdigest(),
        "status": item.get("status"),
        "arguments_body_retained": False,
        "result_body_retained": False,
    }


def _host_mcp_audit_events(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "event_type": "host_mcp_tool_call_audit",
            "classification": _mcp_tool_classification(str(row.get("tool", ""))),
            "server": "chemworld_lab",
            "tool": row.get("tool"),
            "arguments_sha256": row.get("arguments_sha256"),
            "argument_keys": row.get("argument_keys", []),
            "status": "called",
            "arguments_body_retained": False,
            "result_body_retained": False,
        }
        for row in rows
    ]


def _normalize_usage(raw: Mapping[str, Any]) -> dict[str, int]:
    prompt = _nonnegative_int(raw.get("input_tokens"))
    completion = _nonnegative_int(raw.get("output_tokens"))
    cached = min(_nonnegative_int(raw.get("cached_input_tokens")), prompt)
    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": prompt + completion,
        "prompt_cache_hit_tokens": cached,
        "prompt_cache_miss_tokens": prompt - cached,
        "prompt_cache_write_tokens": _nonnegative_int(raw.get("cache_write_input_tokens")),
        "reasoning_output_tokens": _nonnegative_int(raw.get("reasoning_output_tokens")),
    }


def _empty_usage() -> dict[str, int]:
    return {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "prompt_cache_hit_tokens": 0,
        "prompt_cache_miss_tokens": 0,
        "prompt_cache_write_tokens": 0,
        "reasoning_output_tokens": 0,
    }


def _merge_usage(total: dict[str, int], usage: Mapping[str, Any]) -> None:
    for key in total:
        total[key] += _nonnegative_int(usage.get(key))


def _usage_complete(usage: Mapping[str, Any]) -> bool:
    prompt = _nonnegative_int(usage.get("prompt_tokens"))
    return (
        prompt > 0
        and _nonnegative_int(usage.get("total_tokens"))
        == prompt + _nonnegative_int(usage.get("completion_tokens"))
        and _nonnegative_int(usage.get("prompt_cache_hit_tokens"))
        + _nonnegative_int(usage.get("prompt_cache_miss_tokens"))
        == prompt
    )


def _nonnegative_int(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0


def _valid_final_payload(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and value.get("status")
        in {"experiment_complete", "batch_discarded", "budget_exhausted", "stopped"}
        and isinstance(value.get("summary"), str)
        and len(value["summary"]) <= 2000
    )


def _system_prompt_hash() -> str:
    return hashlib.sha256(
        (_SYSTEM_PROMPT + "|" + INTERACTIVE_CODEX_EXPERIMENT_VERSION).encode("utf-8")
    ).hexdigest()


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


__all__ = [
    "DEFAULT_FINALIZATION_TIMEOUT_S",
    "INTERACTIVE_CODEX_EXPERIMENT_VERSION",
    "InteractiveCodexExperimentAgent",
    "InteractiveCodexExperimentError",
    "ProcessFactory",
]
