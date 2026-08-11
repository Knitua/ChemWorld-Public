from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from chemworld.agents.interaction import AgentDecisionContext
from chemworld.agents.interactive_codex_experiment import (
    InteractiveCodexExperimentAgent,
    InteractiveCodexExperimentError,
    _public_task_contract,
)


def test_public_task_contract_exposes_composition_and_explicit_closeout() -> None:
    composition = {
        "composition_id": "generated-world",
        "world": {"components": [{"kind": "reaction"}]},
        "task": {"resources": {"operation_budget": 16, "final_assays": 1}},
    }
    contract = _public_task_contract(
        {
            "task_id": "generated-world",
            "task_contract_hash": "a" * 64,
            "composition": composition,
            "allowed_operations": ["terminate", "measure"],
            "allowed_instruments": ["final_assay"],
            "method_budget_contract": {"complete_experiment_limit": 1},
        }
    )
    assert contract["composition"] == composition
    assert contract["experiment_lifecycle"] == {
        "schema_version": "chemworld-public-experiment-lifecycle-0.1",
        "planned_complete_experiments": 1,
        "explicit_terminate_required": True,
        "final_assay_required": True,
        "final_assay_after_terminate": True,
        "automatic_closeout": False,
    }


def _context(step: int, remaining: int) -> AgentDecisionContext:
    return AgentDecisionContext(
        step=step,
        task_id="reaction-to-assay",
        decision_stage="experiment_setup" if step == 1 else "experiment_control",
        campaign_state={
            "remaining_budget": remaining,
            "budget": 10,
            "experiment_index": 0,
            "campaign_resources": {
                "remaining": {
                    "vessel_starts": 6,
                    "material_amount_mol": {"material-M1": 0.2},
                },
                "hard_limits": {"instrument_uses": {"hplc": 4}},
            },
        },
        visible_metrics={"cost": 0.1 * (step - 1), "score": 0.0},
        latest_spectra={"has_spectral_packet": False},
        uncertainty={},
        constraint_flags={},
        available_operations=("add_reagent", "terminate"),
        previous_event_type=None if step == 1 else "operation_result",
    )


def _action(operation: str, fields: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "operation": operation,
        "valid": True,
        "schema": {
            "fields": fields,
            "required_fields": [field["field"] for field in fields],
        },
    }


def _view(*, with_raw: bool = False) -> dict[str, Any]:
    raw = (
        {
            "kind": "hplc_chromatogram",
            "axis": [0.0, 1.0, 2.0],
            "intensity": [0.1, 0.8, 0.2],
        }
        if with_raw
        else {}
    )
    return {
        "tool_json": {
            "available_actions": [
                _action(
                    "add_reagent",
                    [
                        {
                            "field": "amount_mol",
                            "bounds": {"low": 0.0, "high": 0.04},
                        }
                    ],
                ),
                _action("terminate", []),
                _action(
                    "add_solvent",
                    [
                        {
                            "field": "solvent",
                            "choices": [0, 1],
                            "choice_labels": {
                                "0": "solvent-S1",
                                "1": "solvent-S2",
                            },
                        },
                        {
                            "field": "volume_L",
                            "bounds": {"low": 0.0, "high": 0.05},
                        },
                    ],
                ),
            ],
            "raw_signal": raw,
            "processed_estimate": {"yield": 0.4} if with_raw else {},
        }
    }


_FAKE_CODEX = r"""
import json
import subprocess
import sys
from pathlib import Path

agent = Path(sys.argv[1])

def emit(value):
    print(json.dumps(value, separators=(",", ":")), flush=True)

emit({"type": "thread.started", "thread_id": "fake-thread"})
actions = [
    {"operation": "add_reagent", "amount_mol": 0.01},
    {"operation": "terminate"},
]
for index, action in enumerate(actions, start=1):
    result = subprocess.run(
        [
            sys.executable,
            str(agent / "lab_tool.py"),
            "step",
            "--expected-step",
            str(index),
            "--action-json",
            json.dumps(action, separators=(",", ":")),
        ],
        cwd=agent,
        capture_output=True,
        text=True,
        check=False,
    )
    emit({
        "type": "item.completed",
        "item": {
            "id": f"command-{index}",
            "type": "command_execution",
            "command": "python lab_tool.py step --expected-step N --action-json JSON",
            "aggregated_output": result.stdout,
            "exit_code": result.returncode,
            "status": "completed" if result.returncode == 0 else "failed",
        },
    })
    response = json.loads(result.stdout)
    if response.get("experiment_ended") or response.get("budget_exhausted"):
        break
emit({
    "type": "item.completed",
    "item": {
        "id": "final",
        "type": "agent_message",
        "text": json.dumps({
            "status": "experiment_complete",
            "summary": "The experiment was closed after the declared operations."
        }),
    },
})
emit({
    "type": "turn.completed",
    "usage": {
        "input_tokens": 1234,
        "cached_input_tokens": 234,
        "cache_write_input_tokens": 100,
        "output_tokens": 321,
        "reasoning_output_tokens": 200,
    },
})
"""

_FAKE_FINAL_ASSAY = r"""
import json
import subprocess
import sys
from pathlib import Path

agent = Path(sys.argv[1])

def emit(value):
    print(json.dumps(value, separators=(",", ":")), flush=True)

emit({"type": "thread.started", "thread_id": "fake-final-thread"})
action = {"operation": "measure", "instrument": "final_assay"}
result = subprocess.run(
    [
        sys.executable,
        str(agent / "lab_tool.py"),
        "step",
        "--expected-step",
        "1",
        "--action-json",
        json.dumps(action, separators=(",", ":")),
    ],
    cwd=agent,
    capture_output=True,
    text=True,
    check=False,
)
emit({
    "type": "item.completed",
    "item": {
        "id": "command-final",
        "type": "command_execution",
        "command": "python lab_tool.py step --expected-step 1 --action-json JSON",
        "aggregated_output": result.stdout,
        "exit_code": result.returncode,
        "status": "completed" if result.returncode == 0 else "failed",
    },
})
emit({
    "type": "item.completed",
    "item": {
        "id": "final",
        "type": "agent_message",
        "text": json.dumps({
            "status": "experiment_complete",
            "summary": "A successful final assay completed the experiment.",
        }),
    },
})
emit({
    "type": "turn.completed",
    "usage": {
        "input_tokens": 800,
        "cached_input_tokens": 100,
        "output_tokens": 200,
    },
})
"""

_FAKE_TAMPER_BEFORE_ACTION = r"""
import json
import time
import sys
from pathlib import Path

agent = Path(sys.argv[1])
root = agent.parent
active = json.loads((root / ".ipc" / "active_session.json").read_text(encoding="utf-8"))
session_id = active["session_id"]
request = {
    "schema_version": active["schema_version"],
    "session_id": session_id,
    "request_id": "tampered-request",
    "expected_step": 1,
    "action": {"operation": "terminate"},
}
request_path = agent / ".transport" / session_id / "requests" / "tampered-request.json"
request_path.write_text(json.dumps(request), encoding="utf-8")
(agent / "lab_tool.py").write_text("# tampered", encoding="utf-8")
time.sleep(10)
"""

_FAKE_TAMPER_AFTER_TERMINAL_RESPONSE = r"""
import json
import subprocess
import sys
from pathlib import Path

agent = Path(sys.argv[1])

def emit(value):
    print(json.dumps(value, separators=(",", ":")), flush=True)

emit({"type": "thread.started", "thread_id": "fake-tamper-thread"})
result = subprocess.run(
    [
        sys.executable,
        str(agent / "lab_tool.py"),
        "step",
        "--expected-step",
        "1",
        "--action-json",
        '{"operation":"terminate"}',
    ],
    cwd=agent,
    capture_output=True,
    text=True,
    check=False,
)
(agent / "lab_tool.py").write_text("# tampered after response", encoding="utf-8")
emit({
    "type": "item.completed",
    "item": {
        "id": "command-terminal",
        "type": "command_execution",
        "command": "python lab_tool.py step --expected-step 1 --action-json JSON",
        "aggregated_output": result.stdout,
        "exit_code": result.returncode,
        "status": "completed" if result.returncode == 0 else "failed",
    },
})
emit({
    "type": "item.completed",
    "item": {
        "id": "final",
        "type": "agent_message",
        "text": json.dumps({
            "status": "experiment_complete",
            "summary": "Terminal response received.",
        }),
    },
})
emit({
    "type": "turn.completed",
    "usage": {"input_tokens": 100, "output_tokens": 20},
})
"""


def _fake_process_factory(
    commands: list[list[str]],
    prompts: list[str],
    *,
    script: str = _FAKE_CODEX,
):
    def factory(command: Any, prompt: str, cwd: Path):
        commands.append(list(command))
        prompts.append(prompt)
        return subprocess.Popen(
            [sys.executable, "-c", script, str(cwd)],
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

    return factory


def test_custom_provider_command_uses_responses_and_no_secret(
    tmp_path: Path,
) -> None:
    agent = InteractiveCodexExperimentAgent(
        workspace=tmp_path / "workspace",
        role_id="test",
        model_provider="wellau",
        model_provider_name="WellAU",
        model_provider_base_url="https://api.wellau.com/v1",
        model_provider_env_key="WELLAU_API_KEY",
        process_factory=lambda command, prompt, cwd: None,
    )
    command = agent._command(
        instructions_path=tmp_path / "instructions.md",
        schema_path=tmp_path / "schema.json",
    )
    joined = " ".join(command)
    assert 'approval_policy="never"' in joined
    assert "approvals_reviewer" not in joined
    assert "mcp_servers.chemworld_lab.command" in joined
    assert "chemworld.agents.experiment_codex_mcp" in joined
    assert 'model_provider="wellau"' in joined
    assert 'model_providers.wellau.name="WellAU"' in joined
    assert 'model_providers.wellau.base_url="https://api.wellau.com/v1"' in joined
    assert 'model_providers.wellau.env_key="WELLAU_API_KEY"' in joined
    assert 'model_providers.wellau.wire_api="responses"' in joined
    assert "sk-live" not in joined.lower()


def test_one_codex_process_controls_two_runner_operations(
    tmp_path: Path,
) -> None:
    commands: list[list[str]] = []
    prompts: list[str] = []
    task_info = {
        "task_id": "reaction-to-assay",
        "objective": "balanced",
        "budget": 10,
        "episode_mode": "single_experiment",
        "experiment_lifecycle": {
            "terminate_effect": "only final assay becomes legal",
        },
        "scoring_contract": {"contract_id": "score-v1", "yield_weight": 0.5},
        "material_information": {"mode": "anonymous_nominal_properties"},
        "material_catalog": {
            "solvent-S1": {"secret_property_value": 12.3},
        },
    }
    agent = InteractiveCodexExperimentAgent(
        workspace=tmp_path / "workspace",
        role_id="interactive-test",
        process_factory=_fake_process_factory(commands, prompts),
        request_timeout_s=5.0,
        finalization_timeout_s=5.0,
    )
    agent.reset(task_info, seed=0)
    assert agent.workspace.snapshot_agent_files() == {}

    first = agent.act_with_public_view(_context(1, 10), _view())
    assert first == {"operation": "add_reagent", "amount_mol": 0.01}
    current = json.loads(agent.workspace.current_path.read_text(encoding="utf-8"))
    assert current["campaign_resources"]["remaining"]["vessel_starts"] == 6
    assert current["campaign_resources"]["remaining"]["material_amount_mol"]["material-M1"] == 0.2
    solvent = next(item for item in current["legal_actions"] if item["operation"] == "add_solvent")
    assert solvent["solvent"]["choice_labels"]["0"] == "solvent-S1"
    assert agent.method_resource_usage()["provider_usage_pending"] is True
    assert agent.method_resource_usage()["in_flight_model_call_count"] == 1
    agent.update(
        first,
        {"cost": 0.1, "score": 0.0},
        0.0,
        {
            "transaction_status": "committed",
            "operation_type": "add_reagent",
            "experiment_ended": False,
            "observed_keys": ["cost", "score"],
            "constraint_flags": {},
        },
    )

    second = agent.act_with_public_view(_context(2, 9), _view(with_raw=True))
    assert second == {"operation": "terminate"}
    agent.update(
        second,
        {"cost": 0.1, "score": 0.2},
        0.2,
        {
            "transaction_status": "committed",
            "operation_type": "terminate",
            "experiment_ended": True,
            "observed_keys": ["cost", "score"],
            "constraint_flags": {},
            "leaderboard_score": 0.2,
        },
    )

    assert len(commands) == 1
    assert "--ephemeral" in commands[0]
    assert "--sandbox" in commands[0]
    assert commands[0][-1] == str(agent.workspace.agent_directory)
    assert "secret_property_value" not in prompts[0]
    assert "../reference/material_information.json" in prompts[0]
    assert "chemworld_lab" in prompts[0]
    assert "host-owned STDIO MCP" in prompts[0]
    assert "python lab_tool.py" not in prompts[0]
    assert "score-v1" in prompts[0]
    usage = agent.method_resource_usage()
    assert usage["provider_usage_pending"] is False
    assert usage["input_token_count"] == 1234
    assert usage["output_token_count"] == 321
    receipt = agent.provider_receipts()[0]
    assert receipt["usage"]["reasoning_output_tokens"] == 200
    assert receipt["final_payload_summary"].startswith("The experiment")
    assert receipt["lab_tool_integrity_verified_after_session"] is True
    assert receipt["mcp_tool_integrity_verified_after_session"] is True
    assert receipt["experiment_tool_integrity_verified_after_session"] is True
    assert receipt["private_reasoning_retained"] is False
    assert len(receipt["tool_events"]) == 2
    assert all(event["output_body_retained"] is False for event in receipt["tool_events"])
    assert agent.workspace.snapshot_agent_files() == {}
    assert list((tmp_path / "workspace" / "public" / "artifacts").glob("*.json")) == []
    assert list(agent.workspace.sessions_directory.iterdir()) == []
    assert list(agent.workspace.transport_directory.iterdir()) == []
    assert not (agent.workspace.agent_directory / "request.json").exists()


def test_measurement_artifact_is_immutable_across_update_and_next_state(
    tmp_path: Path,
) -> None:
    def unused_factory(command: Any, prompt: str, cwd: Path):
        del command, prompt, cwd
        raise AssertionError("no process should be launched")

    agent = InteractiveCodexExperimentAgent(
        workspace=tmp_path / "workspace",
        role_id="artifact-test",
        process_factory=unused_factory,
    )
    agent.reset({"task_id": "x", "budget": 3}, seed=0)
    action = {"operation": "measure", "instrument": "uvvis"}
    raw = _view(with_raw=True)["tool_json"]["raw_signal"]
    artifact = agent._publish_outcome_artifact(
        event_id="runner-operation-0001",
        action=action,
        info={"raw_signal": raw},
    )
    assert artifact is not None
    agent._pending_outcome = {
        "event_id": "runner-operation-0001",
        "action": action,
        "artifact": artifact,
    }

    assert agent._publish_latest_artifact(_view(with_raw=True)) == artifact
    assert len(list(agent.workspace.artifacts_directory.glob("*.json"))) == 1


def test_final_assay_or_termination_is_never_added_by_host(tmp_path: Path) -> None:
    commands: list[list[str]] = []
    prompts: list[str] = []
    agent = InteractiveCodexExperimentAgent(
        workspace=tmp_path / "workspace",
        role_id="interactive-test",
        process_factory=_fake_process_factory(commands, prompts),
        request_timeout_s=5.0,
        finalization_timeout_s=5.0,
    )
    agent.reset({"task_id": "x", "budget": 1}, seed=0)
    action = agent.act_with_public_view(_context(1, 1), _view())
    assert action["operation"] == "add_reagent"
    agent.update(
        action,
        {"score": 0.0},
        0.0,
        {
            "transaction_status": "committed",
            "operation_type": "add_reagent",
            "experiment_ended": False,
            "observed_keys": ["score"],
            "constraint_flags": {},
        },
    )
    receipt = agent.provider_receipts()[0]
    assert receipt["terminal_reason"] == "budget_exhausted"
    history = [
        json.loads(line)
        for line in agent.workspace.history_path.read_text(encoding="utf-8").splitlines()
    ]
    assert [event["action"]["operation"] for event in history] == ["add_reagent"]


def test_successful_single_experiment_final_assay_finalizes_without_info_flag(
    tmp_path: Path,
) -> None:
    commands: list[list[str]] = []
    prompts: list[str] = []
    agent = InteractiveCodexExperimentAgent(
        workspace=tmp_path / "workspace",
        role_id="interactive-test",
        process_factory=_fake_process_factory(
            commands,
            prompts,
            script=_FAKE_FINAL_ASSAY,
        ),
        request_timeout_s=5.0,
        finalization_timeout_s=5.0,
    )
    agent.reset({"task_id": "x", "budget": 10}, seed=0)
    action = agent.act_with_public_view(_context(1, 10), _view())
    assert action == {"operation": "measure", "instrument": "final_assay"}
    agent.update(
        action,
        {"score": 0.7},
        0.7,
        {
            "transaction_status": "committed",
            "operation_type": "measure",
            "instrument": "final_assay",
            "experiment_ended": False,
            "leaderboard_score": 0.7,
            "observed_keys": ["score"],
            "constraint_flags": {},
        },
    )

    receipt = agent.provider_receipts()[0]
    assert receipt["terminal_reason"] == "experiment_complete"
    assert agent.method_resource_usage()["provider_usage_pending"] is False


def test_process_exit_before_action_is_fail_closed_after_bounded_restart(
    tmp_path: Path,
) -> None:
    calls = 0

    def factory(command: Any, prompt: str, cwd: Path):
        nonlocal calls
        del command, prompt
        calls += 1
        return subprocess.Popen(
            [sys.executable, "-c", "raise SystemExit(0)"],
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

    agent = InteractiveCodexExperimentAgent(
        workspace=tmp_path / "workspace",
        role_id="interactive-test",
        process_factory=factory,
        request_timeout_s=1.0,
        finalization_timeout_s=1.0,
        pre_action_restart_limit=1,
    )
    agent.reset({"task_id": "x", "budget": 2}, seed=0)
    with pytest.raises(InteractiveCodexExperimentError, match="no fallback"):
        agent.act_with_public_view(_context(1, 2), _view())
    assert calls == 2
    assert len(agent.provider_receipts()) == 2
    assert all(
        receipt["status"] == "interrupted_before_next_action"
        for receipt in agent.provider_receipts()
    )
    assert agent.workspace.history_path.read_text(encoding="utf-8") == ""


def test_lab_tool_tamper_is_rejected_before_action_acceptance(tmp_path: Path) -> None:
    commands: list[list[str]] = []
    prompts: list[str] = []
    agent = InteractiveCodexExperimentAgent(
        workspace=tmp_path / "workspace",
        role_id="tamper-test",
        process_factory=_fake_process_factory(
            commands,
            prompts,
            script=_FAKE_TAMPER_BEFORE_ACTION,
        ),
        request_timeout_s=5.0,
        finalization_timeout_s=2.0,
        pre_action_restart_limit=0,
    )
    agent.reset({"task_id": "x", "budget": 2}, seed=0)

    with pytest.raises(InteractiveCodexExperimentError, match="modified"):
        agent.act_with_public_view(_context(1, 2), _view())

    assert agent.workspace.history_path.read_text(encoding="utf-8") == ""
    assert agent.provider_receipts()[0]["lab_tool_integrity_verified_after_session"] is False


def test_lab_tool_tamper_after_terminal_response_fails_post_session_check(
    tmp_path: Path,
) -> None:
    commands: list[list[str]] = []
    prompts: list[str] = []
    agent = InteractiveCodexExperimentAgent(
        workspace=tmp_path / "workspace",
        role_id="tamper-test",
        process_factory=_fake_process_factory(
            commands,
            prompts,
            script=_FAKE_TAMPER_AFTER_TERMINAL_RESPONSE,
        ),
        request_timeout_s=5.0,
        finalization_timeout_s=5.0,
    )
    agent.reset({"task_id": "x", "budget": 2}, seed=0)
    action = agent.act_with_public_view(_context(1, 2), _view())
    assert action == {"operation": "terminate"}

    with pytest.raises(InteractiveCodexExperimentError, match="post-session integrity"):
        agent.update(
            action,
            {"score": 0.2},
            0.2,
            {
                "transaction_status": "committed",
                "operation_type": "terminate",
                "experiment_ended": True,
                "observed_keys": ["score"],
                "constraint_flags": {},
            },
        )

    assert agent.provider_receipts()[0]["lab_tool_integrity_verified_after_session"] is False


def test_campaign_can_start_fresh_exec_while_agent_directory_persists(
    tmp_path: Path,
) -> None:
    commands: list[list[str]] = []
    prompts: list[str] = []
    agent = InteractiveCodexExperimentAgent(
        workspace=tmp_path / "workspace",
        role_id="interactive-test",
        process_factory=_fake_process_factory(commands, prompts),
        request_timeout_s=5.0,
        finalization_timeout_s=5.0,
    )
    agent.reset({"task_id": "campaign", "budget": 10}, seed=0)
    memory = agent.workspace.agent_directory / "hypotheses.md"
    memory.write_text("persistent agent-authored hypothesis", encoding="utf-8")

    first = agent.act_with_public_view(_context(1, 10), _view())
    agent.update(
        first,
        {"score": 0.1},
        0.1,
        {
            "transaction_status": "committed",
            "operation_type": first["operation"],
            "experiment_ended": True,
            "observed_keys": ["score"],
            "constraint_flags": {},
        },
    )
    second = agent.act_with_public_view(_context(2, 9), _view())
    agent.update(
        second,
        {"score": 0.2},
        0.2,
        {
            "transaction_status": "committed",
            "operation_type": second["operation"],
            "experiment_ended": True,
            "observed_keys": ["score"],
            "constraint_flags": {},
        },
    )

    assert len(commands) == 2
    assert len(agent.provider_receipts()) == 2
    assert memory.read_text(encoding="utf-8") == "persistent agent-authored hypothesis"
