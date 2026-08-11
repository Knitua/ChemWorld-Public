"""Public, replayable process-time envelopes for composed worlds.

The composition layer may attach one policy to ``task.resources``.  The
policy separates the maximum time required by a frozen workflow from a small,
explicit repeat allowance and conservative time allowances for operations
whose runtime duration is state-dependent or implicit (for example quench and
material transfer).
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

PROCESS_TIME_BUDGET_POLICY_VERSION = "chemworld-process-time-budget-policy-0.2"


def _finite_nonnegative(value: Any, *, name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be numeric")
    number = float(value)
    if not math.isfinite(number) or number < 0.0:
        raise ValueError(f"{name} must be finite and non-negative")
    return number


def _nonnegative_int(value: Any, *, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return int(value)


def _normalized_float_map(value: Any, *, name: str) -> dict[str, float]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be an object")
    return {
        str(key): _finite_nonnegative(item, name=f"{name}.{key}")
        for key, item in sorted(value.items())
    }


def _normalized_int_map(value: Any, *, name: str) -> dict[str, int]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be an object")
    return {
        str(key): _nonnegative_int(item, name=f"{name}.{key}")
        for key, item in sorted(value.items())
    }


@dataclass(frozen=True)
class ProcessTimeBudgetPolicy:
    """A task-pattern-specific, predeclared process-time envelope."""

    policy_id: str
    pattern_id: str
    timed_stage_max_s: float
    implicit_stage_reserve_s: float
    required_stage_max_s: float
    repeat_allowance_s: float
    implicit_operation_allowance_s: Mapping[str, float]
    required_operation_counts: Mapping[str, int]
    additional_repeat_limits: Mapping[str, int]
    operation_repeat_limits: Mapping[str, int]
    operation_reference_max_s: Mapping[str, float]
    process_time_limit_s: float
    schema_version: str = PROCESS_TIME_BUDGET_POLICY_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != PROCESS_TIME_BUDGET_POLICY_VERSION:
            raise ValueError("unsupported process-time budget policy schema")
        if not self.policy_id.strip() or not self.pattern_id.strip():
            raise ValueError("process-time policy identifiers must be non-empty")
        required = _finite_nonnegative(
            self.required_stage_max_s,
            name="required_stage_max_s",
        )
        timed = _finite_nonnegative(
            self.timed_stage_max_s,
            name="timed_stage_max_s",
        )
        implicit_reserve = _finite_nonnegative(
            self.implicit_stage_reserve_s,
            name="implicit_stage_reserve_s",
        )
        repeat = _finite_nonnegative(
            self.repeat_allowance_s,
            name="repeat_allowance_s",
        )
        limit = _finite_nonnegative(
            self.process_time_limit_s,
            name="process_time_limit_s",
        )
        if not math.isclose(limit, required + repeat, rel_tol=0.0, abs_tol=1.0e-9):
            raise ValueError(
                "process_time_limit_s must equal required_stage_max_s + repeat_allowance_s"
            )
        if not math.isclose(
            required,
            timed + implicit_reserve,
            rel_tol=0.0,
            abs_tol=1.0e-9,
        ):
            raise ValueError(
                "required_stage_max_s must equal timed_stage_max_s + "
                "implicit_stage_reserve_s"
            )
        implicit = _normalized_float_map(
            self.implicit_operation_allowance_s,
            name="implicit_operation_allowance_s",
        )
        required_counts = _normalized_int_map(
            self.required_operation_counts,
            name="required_operation_counts",
        )
        additional = _normalized_int_map(
            self.additional_repeat_limits,
            name="additional_repeat_limits",
        )
        limits = _normalized_int_map(
            self.operation_repeat_limits,
            name="operation_repeat_limits",
        )
        references = _normalized_float_map(
            self.operation_reference_max_s,
            name="operation_reference_max_s",
        )
        expected_limits = {
            operation: required_counts.get(operation, 0) + additional.get(operation, 0)
            for operation in sorted(set(required_counts) | set(additional))
        }
        if limits != expected_limits:
            raise ValueError(
                "operation_repeat_limits must equal required counts plus additional repeats"
            )
        object.__setattr__(self, "required_stage_max_s", required)
        object.__setattr__(self, "timed_stage_max_s", timed)
        object.__setattr__(self, "implicit_stage_reserve_s", implicit_reserve)
        object.__setattr__(self, "repeat_allowance_s", repeat)
        object.__setattr__(self, "process_time_limit_s", limit)
        object.__setattr__(self, "implicit_operation_allowance_s", implicit)
        object.__setattr__(self, "required_operation_counts", required_counts)
        object.__setattr__(self, "additional_repeat_limits", additional)
        object.__setattr__(self, "operation_repeat_limits", limits)
        object.__setattr__(self, "operation_reference_max_s", references)

    def proposed_time_s(self, action: Mapping[str, Any]) -> float:
        """Return the conservative time reservation for one proposed action."""

        operation = str(action.get("operation", ""))
        duration = action.get("duration_s")
        if duration is not None and not isinstance(duration, bool):
            try:
                candidate = float(duration)
            except (TypeError, ValueError):
                candidate = 0.0
            if math.isfinite(candidate) and candidate > 0.0:
                return candidate
        return float(self.implicit_operation_allowance_s.get(operation, 0.0))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "policy_id": self.policy_id,
            "pattern_id": self.pattern_id,
            "formula": (
                "timed_stage_max_s + implicit_stage_reserve_s + repeat_allowance_s; "
                "implicit quench/transfer durations are reserved in the required "
                "stage envelope before commit"
            ),
            "timed_stage_max_s": self.timed_stage_max_s,
            "implicit_stage_reserve_s": self.implicit_stage_reserve_s,
            "required_stage_max_s": self.required_stage_max_s,
            "repeat_allowance_s": self.repeat_allowance_s,
            "implicit_operation_allowance_s": dict(
                self.implicit_operation_allowance_s
            ),
            "required_operation_counts": dict(self.required_operation_counts),
            "additional_repeat_limits": dict(self.additional_repeat_limits),
            "operation_repeat_limits": dict(self.operation_repeat_limits),
            "operation_reference_max_s": dict(self.operation_reference_max_s),
            "process_time_limit_s": self.process_time_limit_s,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ProcessTimeBudgetPolicy:
        return cls(
            schema_version=str(payload.get("schema_version", "")),
            policy_id=str(payload.get("policy_id", "")),
            pattern_id=str(payload.get("pattern_id", "")),
            timed_stage_max_s=float(payload.get("timed_stage_max_s", -1.0)),
            implicit_stage_reserve_s=float(
                payload.get("implicit_stage_reserve_s", -1.0)
            ),
            required_stage_max_s=float(payload.get("required_stage_max_s", -1.0)),
            repeat_allowance_s=float(payload.get("repeat_allowance_s", -1.0)),
            implicit_operation_allowance_s=dict(
                payload.get("implicit_operation_allowance_s", {})
            ),
            required_operation_counts=dict(
                payload.get("required_operation_counts", {})
            ),
            additional_repeat_limits=dict(
                payload.get("additional_repeat_limits", {})
            ),
            operation_repeat_limits=dict(payload.get("operation_repeat_limits", {})),
            operation_reference_max_s=dict(
                payload.get("operation_reference_max_s", {})
            ),
            process_time_limit_s=float(payload.get("process_time_limit_s", -1.0)),
        )


def derive_process_time_budget_policy(
    *,
    pattern_id: str,
    workflows: Sequence[Any],
    continuous_axes: Sequence[Any] = (),
    additional_repeat_limits: Mapping[str, int] | None = None,
    implicit_operation_allowance_s: Mapping[str, float] | None = None,
) -> ProcessTimeBudgetPolicy:
    """Derive one policy from frozen workflows and their coverage-axis maxima."""

    axis_upper = {
        str(axis.axis_id): _finite_nonnegative(axis.upper, name=f"axis.{axis.axis_id}.upper")
        for axis in continuous_axes
    }
    implicit = _normalized_float_map(
        implicit_operation_allowance_s or {},
        name="implicit_operation_allowance_s",
    )
    additional = _normalized_int_map(
        additional_repeat_limits or {},
        name="additional_repeat_limits",
    )
    required_counts: dict[str, int] = {}
    reference_max: dict[str, float] = {}
    maximum_workflow_time = 0.0
    maximum_timed_workflow_time = 0.0
    maximum_implicit_workflow_time = 0.0
    for workflow in workflows:
        counts: dict[str, int] = {}
        workflow_time = 0.0
        timed_workflow_time = 0.0
        implicit_workflow_time = 0.0
        actions = getattr(workflow, "actions", ())
        for action in actions:
            if not isinstance(action, Mapping):
                raise ValueError("workflow actions must be mappings")
            operation = str(action.get("operation", ""))
            counts[operation] = counts.get(operation, 0) + 1
            duration_value = action.get("duration_s")
            duration = 0.0
            if isinstance(duration_value, Mapping):
                axis_id = str(duration_value.get("coverage_axis", ""))
                if axis_id not in axis_upper:
                    raise ValueError(
                        f"workflow duration references unknown coverage axis {axis_id!r}"
                    )
                duration = axis_upper[axis_id]
                timed_workflow_time += duration
            elif duration_value is not None:
                duration = _finite_nonnegative(
                    duration_value,
                    name=f"workflow.{operation}.duration_s",
                )
                timed_workflow_time += duration
            else:
                duration = implicit.get(operation, 0.0)
                implicit_workflow_time += duration
            workflow_time += duration
            if duration > 0.0:
                reference_max[operation] = max(reference_max.get(operation, 0.0), duration)
        for operation, count in counts.items():
            required_counts[operation] = max(required_counts.get(operation, 0), count)
        if workflow_time > maximum_workflow_time:
            maximum_workflow_time = workflow_time
            maximum_timed_workflow_time = timed_workflow_time
            maximum_implicit_workflow_time = implicit_workflow_time

    missing_repeat_reference = sorted(
        operation
        for operation in additional
        if operation not in reference_max and operation not in required_counts
    )
    if missing_repeat_reference:
        raise ValueError(
            "additional repeats require a timed or implicit reference: "
            f"{missing_repeat_reference}"
        )
    repeat_allowance = sum(
        reference_max.get(operation, 0.0) * count
        for operation, count in additional.items()
    )
    repeat_limits = {
        operation: required_counts.get(operation, 0) + additional.get(operation, 0)
        for operation in sorted(set(required_counts) | set(additional))
    }
    return ProcessTimeBudgetPolicy(
        policy_id=f"first-paper-{pattern_id}-process-time-v3",
        pattern_id=pattern_id,
        timed_stage_max_s=maximum_timed_workflow_time,
        implicit_stage_reserve_s=maximum_implicit_workflow_time,
        required_stage_max_s=maximum_workflow_time,
        repeat_allowance_s=repeat_allowance,
        implicit_operation_allowance_s=implicit,
        required_operation_counts={
            operation: required_counts[operation]
            for operation in sorted(required_counts)
        },
        additional_repeat_limits=additional,
        operation_repeat_limits=repeat_limits,
        operation_reference_max_s=reference_max,
        process_time_limit_s=maximum_workflow_time + repeat_allowance,
    )


__all__ = [
    "PROCESS_TIME_BUDGET_POLICY_VERSION",
    "ProcessTimeBudgetPolicy",
    "derive_process_time_budget_policy",
]
