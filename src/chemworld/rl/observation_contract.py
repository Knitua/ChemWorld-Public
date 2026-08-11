"""Canonical semantic contract for operation-level RL observations.

An observation-space shape is not enough to decide whether a checkpoint is
compatible with a runtime.  This module freezes the meaning and order of every
coordinate consumed by PPO or SAC so training, checkpoint sidecars, and the
public frozen-policy adapter can bind the same task-specific digest.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from chemworld.agent_interface import rl_observation_spec
from chemworld.operation_validator import OPERATION_AFFORDANCE_STATE_MACHINE_VERSION
from chemworld.rl.rewards import core_operation_requirements
from chemworld.tasks import get_task
from chemworld.world.operations import OPERATION_TYPES

OBSERVATION_CONTRACT_SCHEMA_VERSION = "chemworld-rl-observation-contract-0.2"

CAMPAIGN_PROGRESS_FIELDS: tuple[dict[str, str], ...] = (
    {
        "key": "operation_budget_fraction_used",
        "formula": "min(max(operation_count, 0) / max(budget, 1), 1.0)",
    },
    {
        "key": "operation_budget_fraction_remaining",
        "formula": ("min(max(max(budget, 1) - max(operation_count, 0), 0) / max(budget, 1), 1.0)"),
    },
    {
        "key": "completed_experiment_summary_ratio",
        "formula": ("min(experiment_summary_count / max(max(experiment_index, 0) + 1, 1), 1.0)"),
    },
)


def _sha256_json(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _segment(
    *,
    name: str,
    start: int,
    keys: list[str],
    low: list[float],
    high: list[float],
    source: str,
) -> dict[str, Any]:
    if not keys or len(keys) != len(low) or len(keys) != len(high):
        raise ValueError(f"RL observation segment {name!r} has inconsistent coordinates")
    return {
        "name": name,
        "start": start,
        "stop_exclusive": start + len(keys),
        "length": len(keys),
        "keys": keys,
        "bounds": {"low": low, "high": high},
        "source": source,
    }


def rl_observation_contract(task_id: str) -> dict[str, Any]:
    """Return the task-specific RL observation semantics and canonical digest."""

    task = get_task(task_id)
    public_spec = rl_observation_spec(include_cost=True)
    public_keys = [str(key) for key in public_spec["keys"]]
    public_low = [float(value) for value in public_spec["value_bounds"]["low"]]
    public_high = [float(value) for value in public_spec["value_bounds"]["high"]]
    mask_low = [float(value) for value in public_spec["mask_bounds"]["low"]]
    mask_high = [float(value) for value in public_spec["mask_bounds"]["high"]]
    requirements = core_operation_requirements(
        task.allowed_operations,
        task_id=task_id,
    )

    segments: list[dict[str, Any]] = []
    offset = 0

    def append_segment(
        name: str,
        keys: list[str],
        low: list[float],
        high: list[float],
        source: str,
    ) -> None:
        nonlocal offset
        segment = _segment(
            name=name,
            start=offset,
            keys=keys,
            low=low,
            high=high,
            source=source,
        )
        segments.append(segment)
        offset = int(segment["stop_exclusive"])

    append_segment(
        "public_values",
        public_keys,
        public_low,
        public_high,
        "public rl_view.vector in rl_view.keys order",
    )
    append_segment(
        "public_observed_mask",
        [f"observed::{key}" for key in public_keys],
        mask_low,
        mask_high,
        "public rl_view.mask in rl_view.keys order",
    )
    append_segment(
        "core_operation_progress",
        [f"core_requirement::{index}" for index in range(len(requirements))],
        [0.0] * len(requirements),
        [1.0] * len(requirements),
        "successful public operations in the current physical experiment",
    )
    append_segment(
        "operation_affordance_mask",
        [f"available::{operation}" for operation in OPERATION_TYPES],
        [0.0] * len(OPERATION_TYPES),
        [1.0] * len(OPERATION_TYPES),
        "current public affordance mask in global OPERATION_TYPES order",
    )
    append_segment(
        "campaign_progress",
        [field["key"] for field in CAMPAIGN_PROGRESS_FIELDS],
        [0.0] * len(CAMPAIGN_PROGRESS_FIELDS),
        [1.0] * len(CAMPAIGN_PROGRESS_FIELDS),
        "public campaign_state",
    )

    vector_keys = [key for segment in segments for key in segment["keys"]]
    vector_low = [value for segment in segments for value in segment["bounds"]["low"]]
    vector_high = [value for segment in segments for value in segment["bounds"]["high"]]
    if len(vector_keys) != offset or len(set(vector_keys)) != len(vector_keys):
        raise RuntimeError("RL observation coordinates must be contiguous and unique")

    payload: dict[str, Any] = {
        "schema_version": OBSERVATION_CONTRACT_SCHEMA_VERSION,
        "task_id": task_id,
        "dtype": "float32",
        "shape": [offset],
        "concatenation_order": [segment["name"] for segment in segments],
        "segments": segments,
        "vector_keys": vector_keys,
        "vector_bounds": {"low": vector_low, "high": vector_high},
        "public_view": {
            "schema_version": public_spec["schema_version"],
            "include_cost": True,
            "include_observed_mask": True,
            "missing_value": float(public_spec["missing_value"]),
            "missing_value_requires_zero_mask": True,
            "finite_value_requires_one_mask": True,
        },
        "core_operation_progress": {
            "requirements": [list(group) for group in requirements],
            "group_semantics": "one successful operation from each alternatives group",
            "invalid_precondition_updates_progress": False,
            "repeated_success_is_idempotent": True,
            "reset": "after experiment_ended and at environment or agent reset",
            "public_operation_history_only": True,
        },
        "operation_affordance_mask": {
            "operation_order": list(OPERATION_TYPES),
            "available": 1.0,
            "unavailable": 0.0,
            "state_machine_version": OPERATION_AFFORDANCE_STATE_MACHINE_VERSION,
            "hidden_state_access": False,
        },
        "campaign_progress": {
            "fields": [dict(field) for field in CAMPAIGN_PROGRESS_FIELDS],
            "clipped_to_unit_interval": True,
        },
        "compatibility_policy": {
            "required_match": "exact contract_hash",
            "shape_only_compatible": False,
            "legacy_checkpoint_compatible": False,
        },
    }
    payload["contract_hash"] = _sha256_json(payload)
    return payload


__all__ = [
    "CAMPAIGN_PROGRESS_FIELDS",
    "OBSERVATION_CONTRACT_SCHEMA_VERSION",
    "rl_observation_contract",
]
