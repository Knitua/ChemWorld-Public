"""Fail-closed public message boundary for independent agent subprocesses."""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

from chemworld.agents.task_recipes import (
    task_recipe_dimension,
    task_recipe_from_unit_vector,
)
from chemworld.data.logging import observation_to_json, to_builtin
from chemworld.envs.chemworld_env import ChemWorldEnv
from chemworld.foundation.public_leakage import audit_public_payload
from chemworld.tasks import SERIOUS_TASK_IDS

PROTOCOL_SCHEMA_VERSION = "chemworld-public-harness-protocol-0.1"
REPORT_SCHEMA_VERSION = "chemworld-public-harness-audit-0.1"
MESSAGE_SCHEMA_VERSION = "chemworld-public-harness-message-0.1"
EXECUTION_MODE = "trusted-local-subprocess"
SECURITY_BOUNDARY = "trusted-local-subprocess-not-a-sandbox"

TASK_INFO_ALLOWLIST = frozenset(
    {
        "env_id",
        "task_id",
        "scenario_id",
        "initial_state_id",
        "world_split",
        "objective",
        "budget",
        "official_budget",
        "episode_mode",
        "contract_profile",
        "safety_limit",
        "task_contract_hash",
        "runtime_profile_hash",
        "mechanism_summary",
        "scoring_contract",
        "scoring_contract_hash",
        "observation_contract",
        "observation_contract_hash",
        "operation_types",
        "allowed_operations",
        "allowed_instruments",
        "material_catalog",
        "kernel_maturity",
        "physics_maturity",
        "proxy_allowed",
        "instruments",
        "operations",
        "operation_contracts",
        "observation_keys",
    }
)

STEP_INFO_ALLOWLIST = frozenset(
    {
        "step",
        "budget",
        "remaining_budget",
        "episode_mode",
        "experiment_index",
        "operation_id",
        "experiment_ended",
        "task_id",
        "scenario_id",
        "objective",
        "safety_limit",
        "task_contract_hash",
        "runtime_profile_hash",
        "scoring_contract_hash",
        "observation_contract_hash",
        "operation_type",
        "operation_allowed_by_task",
        "instrument_allowed_by_task",
        "preconditions",
        "state_delta_summary",
        "instrument",
        "instrument_source",
        "observed_keys",
        "observed_mask",
        "raw_signal",
        "processed_estimate",
        "uncertainty",
        "constraint_flags",
        "cost",
        "cost_components",
        "reward_source",
        "transaction_status",
    }
)

PRIVATE_TEXT_KEYS = frozenset(
    {
        "expected_answer",
        "hidden_tests",
        "judge_notes",
        "private_instructions",
        "private_prompt",
        "private_seed",
        "reference_solution",
        "solution",
        "task_text",
        "world_seed",
        "evaluation_seed",
    }
)

TRACEBACK_MARKERS = (
    "traceback (most recent call last)",
    'file "',
    "stack trace",
)
WINDOWS_PATH_PATTERN = re.compile(r"(?:^|[\s\"'])[A-Za-z]:[\\/][^\s\"']+")
POSIX_PATH_PATTERN = re.compile(
    r"(?:^|[\s\"'])/(?:etc|home|private|root|tmp|users|var)(?:/|\\)",
    re.IGNORECASE,
)


class PublicHarnessError(ValueError):
    """A public-boundary message failed closed."""


class StudentProtocolError(RuntimeError):
    """A student subprocess response violated the public protocol."""


@dataclass(frozen=True)
class HarnessPolicy:
    message_limit_bytes: int = 1_000_000
    response_limit_bytes: int = 100_000

    def __post_init__(self) -> None:
        if self.message_limit_bytes <= 0 or self.response_limit_bytes <= 0:
            raise ValueError("public harness byte limits must be positive")


def _contains_nonfinite(value: Any) -> bool:
    if isinstance(value, Mapping):
        return any(_contains_nonfinite(item) for item in value.values())
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return any(_contains_nonfinite(item) for item in value)
    if isinstance(value, np.ndarray):
        return _contains_nonfinite(value.tolist())
    if isinstance(value, np.generic):
        return _contains_nonfinite(value.item())
    return isinstance(value, float) and not math.isfinite(value)


def _json_bytes(payload: Any) -> bytes:
    if _contains_nonfinite(payload):
        raise PublicHarnessError("public payload is not finite JSON")
    try:
        return json.dumps(
            to_builtin(payload),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise PublicHarnessError("public payload is not finite JSON") from error


def _extra_public_findings(payload: Any) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []

    def visit(value: Any, path: str) -> None:
        if isinstance(value, Mapping):
            for key, child in value.items():
                key_text = str(key)
                child_path = f"{path}.{key_text}"
                if key_text.lower() in PRIVATE_TEXT_KEYS:
                    findings.append(
                        {
                            "path": child_path,
                            "reason": "private_task_text_key",
                        }
                    )
                    continue
                visit(child, child_path)
            return
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            for index, child in enumerate(value):
                visit(child, f"{path}[{index}]")
            return
        if not isinstance(value, str):
            return
        lowered = value.lower()
        if any(marker in lowered for marker in TRACEBACK_MARKERS):
            findings.append({"path": path, "reason": "traceback_text"})
        if WINDOWS_PATH_PATTERN.search(value) or POSIX_PATH_PATTERN.search(value):
            findings.append({"path": path, "reason": "absolute_path"})

    visit(payload, "$")
    return findings


def validate_public_payload(
    payload: Any,
    *,
    hidden_species_ids: set[str] | frozenset[str] | None = None,
    max_bytes: int,
) -> int:
    """Validate one teacher-to-student payload and return its encoded size."""

    leakage = [
        finding.to_dict()
        for finding in audit_public_payload(
            payload,
            hidden_species_ids=hidden_species_ids,
        )
    ]
    leakage.extend(_extra_public_findings(payload))
    if leakage:
        reasons = sorted({finding["reason"] for finding in leakage})
        raise PublicHarnessError(f"public payload rejected: {', '.join(reasons)}")
    encoded = _json_bytes(payload)
    if len(encoded) > max_bytes:
        raise PublicHarnessError(
            f"public payload exceeds byte limit ({len(encoded)} > {max_bytes})"
        )
    return len(encoded)


def _allowlisted(payload: Mapping[str, Any], keys: frozenset[str]) -> dict[str, Any]:
    return {key: to_builtin(payload[key]) for key in sorted(keys) if key in payload}


def public_task_info(
    task_info: Mapping[str, Any],
    *,
    hidden_species_ids: set[str] | frozenset[str],
    policy: HarnessPolicy,
) -> dict[str, Any]:
    public = _allowlisted(task_info, TASK_INFO_ALLOWLIST)
    validate_public_payload(
        public,
        hidden_species_ids=hidden_species_ids,
        max_bytes=policy.message_limit_bytes,
    )
    return public


def public_step_info(
    info: Mapping[str, Any],
    *,
    hidden_species_ids: set[str] | frozenset[str],
    policy: HarnessPolicy,
) -> dict[str, Any]:
    public = _allowlisted(info, STEP_INFO_ALLOWLIST)
    validate_public_payload(
        public,
        hidden_species_ids=hidden_species_ids,
        max_bytes=policy.message_limit_bytes,
    )
    return public


def _message(
    message_type: str,
    body: Mapping[str, Any],
    *,
    hidden_species_ids: set[str] | frozenset[str],
    policy: HarnessPolicy,
) -> dict[str, Any]:
    payload = {
        "schema_version": MESSAGE_SCHEMA_VERSION,
        "type": message_type,
        **dict(body),
    }
    validate_public_payload(
        payload,
        hidden_species_ids=hidden_species_ids,
        max_bytes=policy.message_limit_bytes,
    )
    return payload


def reset_request(
    task_info: Mapping[str, Any],
    agent_seed: int,
    *,
    hidden_species_ids: set[str] | frozenset[str],
    policy: HarnessPolicy,
) -> dict[str, Any]:
    return _message(
        "reset",
        {"task_info": task_info, "seed": int(agent_seed)},
        hidden_species_ids=hidden_species_ids,
        policy=policy,
    )


def act_request(
    history: Sequence[Mapping[str, Any]],
    *,
    hidden_species_ids: set[str] | frozenset[str],
    policy: HarnessPolicy,
) -> dict[str, Any]:
    return _message(
        "act",
        {"history": [to_builtin(entry) for entry in history]},
        hidden_species_ids=hidden_species_ids,
        policy=policy,
    )


def update_request(
    *,
    action: Mapping[str, Any],
    observation: Mapping[str, Any],
    reward: float,
    info: Mapping[str, Any],
    hidden_species_ids: set[str] | frozenset[str],
    policy: HarnessPolicy,
) -> dict[str, Any]:
    return _message(
        "update",
        {
            "action": to_builtin(action),
            "observation": to_builtin(observation),
            "reward": float(reward),
            "info": to_builtin(info),
        },
        hidden_species_ids=hidden_species_ids,
        policy=policy,
    )


def history_entry(
    *,
    step: int,
    action: Mapping[str, Any],
    observation: Mapping[str, Any],
    reward: float,
    info: Mapping[str, Any],
    hidden_species_ids: set[str] | frozenset[str],
    policy: HarnessPolicy,
) -> dict[str, Any]:
    entry = {
        "step": int(step),
        "action": to_builtin(action),
        "observation": to_builtin(observation),
        "reward": float(reward),
        "info": to_builtin(info),
    }
    validate_public_payload(
        entry,
        hidden_species_ids=hidden_species_ids,
        max_bytes=policy.message_limit_bytes,
    )
    return entry


def close_request(policy: HarnessPolicy) -> dict[str, Any]:
    return _message(
        "close",
        {},
        hidden_species_ids=frozenset(),
        policy=policy,
    )


def validate_student_response(
    response: Any,
    *,
    request_type: str,
    policy: HarnessPolicy,
) -> dict[str, Any]:
    """Validate student output without reflecting its traceback or paths."""

    if not isinstance(response, dict):
        raise StudentProtocolError("student_protocol_non_object")
    try:
        response_size = len(_json_bytes(response))
    except PublicHarnessError as error:
        raise StudentProtocolError("student_protocol_invalid_json") from error
    if response_size > policy.response_limit_bytes:
        raise StudentProtocolError("student_protocol_response_too_large")
    if response.get("ok") is not True:
        raise StudentProtocolError("student_runtime_reported_error")
    expected_keys = {
        "reset": {"ok", "result"},
        "act": {"ok", "action"},
        "update": {"ok", "result"},
        "close": {"ok", "closed"},
    }.get(request_type)
    if expected_keys is None or set(response) != expected_keys:
        raise StudentProtocolError("student_protocol_response_schema")
    if request_type == "act" and not isinstance(response.get("action"), dict):
        raise StudentProtocolError("student_protocol_action_not_object")
    if request_type == "close" and response.get("closed") is not True:
        raise StudentProtocolError("student_protocol_close_not_acknowledged")
    return response


def policy_from_protocol(protocol: Mapping[str, Any]) -> HarnessPolicy:
    limits = protocol.get("limits")
    if not isinstance(limits, Mapping):
        raise ValueError("public harness protocol requires limits")
    message_limit = limits.get("teacher_message_bytes")
    response_limit = limits.get("student_response_bytes")
    if not isinstance(message_limit, int) or isinstance(message_limit, bool):
        raise ValueError("teacher_message_bytes must be an integer")
    if not isinstance(response_limit, int) or isinstance(response_limit, bool):
        raise ValueError("student_response_bytes must be an integer")
    return HarnessPolicy(message_limit, response_limit)


def audit_public_message_contract(protocol: Mapping[str, Any]) -> dict[str, Any]:
    """Exercise reset/act/update/history messages on all serious tasks."""

    raw_tasks = protocol.get("task_ids")
    task_ids = (
        [task_id for task_id in raw_tasks if isinstance(task_id, str)]
        if isinstance(raw_tasks, list)
        else []
    )
    checks = {
        "schema": protocol.get("schema_version") == PROTOCOL_SCHEMA_VERSION,
        "candidate_is_non_claiming": protocol.get("status") == "candidate_non_claiming",
        "execution_mode": protocol.get("execution_mode") == EXECUTION_MODE,
        "sandbox_claim_disabled": protocol.get("sandbox_ready") is False,
        "agent_seed_is_decoupled": protocol.get("agent_seed_policy") == "fixed_public_zero",
        "task_scope": task_ids == list(SERIOUS_TASK_IDS),
    }
    task_reports: dict[str, Any] = {}
    configuration_error: str | None = None
    max_message_bytes = 0
    negative_probes = {
        "hidden_state_fail_closed": False,
        "private_task_text_fail_closed": False,
        "traceback_fail_closed": False,
        "absolute_path_fail_closed": False,
    }
    if all(checks.values()):
        try:
            policy = policy_from_protocol(protocol)
            for task_id in task_ids:
                env = ChemWorldEnv(task_id=task_id, seed=0)
                try:
                    observation, task_info = env.reset(seed=0)
                    hidden_species = set(env.scenario_instance.compiled_mechanism.species_index)
                    safe_task = public_task_info(
                        task_info,
                        hidden_species_ids=hidden_species,
                        policy=policy,
                    )
                    reset = reset_request(
                        safe_task,
                        0,
                        hidden_species_ids=hidden_species,
                        policy=policy,
                    )
                    first_act = act_request(
                        [],
                        hidden_species_ids=hidden_species,
                        policy=policy,
                    )
                    dimension = task_recipe_dimension(task_info)
                    recipe = task_recipe_from_unit_vector(
                        task_info,
                        np.full(dimension, 0.5, dtype=float),
                    )
                    action = recipe["steps"][0]
                    observation, reward, _terminated, _truncated, info = env.step(action)
                    observation_json = observation_to_json(observation)
                    safe_info = public_step_info(
                        info,
                        hidden_species_ids=hidden_species,
                        policy=policy,
                    )
                    update = update_request(
                        action=action,
                        observation=observation_json,
                        reward=float(reward),
                        info=safe_info,
                        hidden_species_ids=hidden_species,
                        policy=policy,
                    )
                    entry = history_entry(
                        step=1,
                        action=action,
                        observation=observation_json,
                        reward=float(reward),
                        info=safe_info,
                        hidden_species_ids=hidden_species,
                        policy=policy,
                    )
                    next_act = act_request(
                        [entry],
                        hidden_species_ids=hidden_species,
                        policy=policy,
                    )
                    sizes = [
                        len(_json_bytes(message))
                        for message in (reset, first_act, update, next_act)
                    ]
                    max_message_bytes = max(max_message_bytes, *sizes)
                    task_reports[task_id] = {
                        "message_types": ["reset", "act", "update", "act_with_history"],
                        "max_message_bytes": max(sizes),
                        "hidden_species_count": len(hidden_species),
                        "passed": True,
                    }
                finally:
                    env.close()

            try:
                validate_public_payload(
                    {"hidden_parameters": {"theta": [1.0]}},
                    max_bytes=policy.message_limit_bytes,
                )
            except PublicHarnessError:
                negative_probes["hidden_state_fail_closed"] = True
            try:
                validate_public_payload(
                    {"private_prompt": "secret task answer"},
                    max_bytes=policy.message_limit_bytes,
                )
            except PublicHarnessError:
                negative_probes["private_task_text_fail_closed"] = True
            try:
                validate_public_payload(
                    {"message": 'Traceback (most recent call last): File "agent.py"'},
                    max_bytes=policy.message_limit_bytes,
                )
            except PublicHarnessError:
                negative_probes["traceback_fail_closed"] = True
            try:
                validate_public_payload(
                    {"message": "failed at C:\\private\\teacher\\config.json"},
                    max_bytes=policy.message_limit_bytes,
                )
            except PublicHarnessError:
                negative_probes["absolute_path_fail_closed"] = True
        except (IndexError, KeyError, TypeError, ValueError) as error:
            configuration_error = str(error)

    checks["task_messages"] = len(task_reports) == len(SERIOUS_TASK_IDS) and all(
        report["passed"] for report in task_reports.values()
    )
    checks.update(negative_probes)
    message_controls_ready = all(checks.values()) and configuration_error is None
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "protocol_id": protocol.get("protocol_id"),
        "execution_mode": EXECUTION_MODE,
        "security_boundary": SECURITY_BOUNDARY,
        "message_controls_ready": message_controls_ready,
        "sandbox_ready": False,
        "checks": checks,
        "configuration_error": configuration_error,
        "max_teacher_message_bytes": max_message_bytes,
        "tasks": task_reports,
    }


__all__ = [
    "EXECUTION_MODE",
    "MESSAGE_SCHEMA_VERSION",
    "PROTOCOL_SCHEMA_VERSION",
    "REPORT_SCHEMA_VERSION",
    "SECURITY_BOUNDARY",
    "HarnessPolicy",
    "PublicHarnessError",
    "StudentProtocolError",
    "act_request",
    "audit_public_message_contract",
    "close_request",
    "history_entry",
    "policy_from_protocol",
    "public_step_info",
    "public_task_info",
    "reset_request",
    "update_request",
    "validate_public_payload",
    "validate_student_response",
]
