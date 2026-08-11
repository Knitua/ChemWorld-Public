"""Preregistered physical and observation divergence oracles for world forks."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal, cast

from chemworld.foundation.world_fork_manifest import (
    ALLOWED_INTERVENTION_CLASSES,
    InterventionClass,
    WorldComponentInventory,
    canonical_json_sha256,
)
from chemworld.foundation.world_fork_spec import WorldForkSpec

DIVERGENCE_ORACLE_SCHEMA_VERSION = "chemworld-world-fork-divergence-oracle-0.1"
DivergenceChannel = Literal["physical_state", "public_observation"]
DivergenceDirection = Literal["either", "increase", "decrease"]

_EXPECTATION_KEYS = frozenset(
    {
        "expectation_id",
        "channel",
        "checkpoint_id",
        "field_path",
        "direction",
        "minimum_absolute_delta",
        "minimum_relative_delta",
        "relative_scale_floor",
    }
)
_ORACLE_KEYS = frozenset(
    {
        "schema_version",
        "oracle_id",
        "intervention_class",
        "target_component_id",
        "expectations",
    }
)


class DivergenceOracleError(ValueError):
    """Raised when a divergence oracle is malformed or incompatible with a fork."""


def _require_exact_keys(payload: Mapping[str, Any], expected: frozenset[str], label: str) -> None:
    actual = set(payload)
    if actual != expected:
        raise DivergenceOracleError(
            f"{label} fields do not match schema: missing={sorted(expected - actual)}, "
            f"unknown={sorted(actual - expected)}"
        )


def _finite_nonnegative(value: Any, label: str) -> float:
    if isinstance(value, bool):
        raise DivergenceOracleError(f"{label} must be finite and non-negative")
    number = float(value)
    if not math.isfinite(number) or number < 0.0:
        raise DivergenceOracleError(f"{label} must be finite and non-negative")
    return number


def _finite_positive(value: Any, label: str) -> float:
    number = _finite_nonnegative(value, label)
    if number == 0.0:
        raise DivergenceOracleError(f"{label} must be positive")
    return number


@dataclass(frozen=True)
class DivergenceExpectation:
    """One numeric response expected to differ at an aligned checkpoint."""

    expectation_id: str
    channel: DivergenceChannel
    checkpoint_id: str
    field_path: tuple[str, ...]
    direction: DivergenceDirection
    minimum_absolute_delta: float
    minimum_relative_delta: float
    relative_scale_floor: float

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> DivergenceExpectation:
        _require_exact_keys(payload, _EXPECTATION_KEYS, "divergence_expectation")
        raw_path = payload["field_path"]
        if (
            not isinstance(raw_path, list)
            or not raw_path
            or not all(isinstance(item, str) and item for item in raw_path)
        ):
            raise DivergenceOracleError("field_path must be a non-empty string list")
        expectation = cls(
            expectation_id=str(payload["expectation_id"]),
            channel=cast(DivergenceChannel, str(payload["channel"])),
            checkpoint_id=str(payload["checkpoint_id"]),
            field_path=tuple(raw_path),
            direction=cast(DivergenceDirection, str(payload["direction"])),
            minimum_absolute_delta=_finite_nonnegative(
                payload["minimum_absolute_delta"], "minimum_absolute_delta"
            ),
            minimum_relative_delta=_finite_nonnegative(
                payload["minimum_relative_delta"], "minimum_relative_delta"
            ),
            relative_scale_floor=_finite_positive(
                payload["relative_scale_floor"], "relative_scale_floor"
            ),
        )
        expectation.validate()
        return expectation

    def validate(self) -> None:
        if not self.expectation_id or not self.checkpoint_id:
            raise DivergenceOracleError("expectation_id and checkpoint_id are required")
        if self.channel not in {"physical_state", "public_observation"}:
            raise DivergenceOracleError("unsupported divergence channel")
        if self.direction not in {"either", "increase", "decrease"}:
            raise DivergenceOracleError("unsupported divergence direction")
        if self.minimum_absolute_delta == 0.0 and self.minimum_relative_delta == 0.0:
            raise DivergenceOracleError("at least one divergence tolerance must be positive")

    def to_dict(self) -> dict[str, Any]:
        return {
            "expectation_id": self.expectation_id,
            "channel": self.channel,
            "checkpoint_id": self.checkpoint_id,
            "field_path": list(self.field_path),
            "direction": self.direction,
            "minimum_absolute_delta": self.minimum_absolute_delta,
            "minimum_relative_delta": self.minimum_relative_delta,
            "relative_scale_floor": self.relative_scale_floor,
        }


@dataclass(frozen=True)
class DivergenceOracleSpec:
    """A content-addressed set of paired physical and observation expectations."""

    oracle_id: str
    intervention_class: InterventionClass
    target_component_id: str
    expectations: tuple[DivergenceExpectation, ...]

    @classmethod
    def from_dict(
        cls,
        payload: Mapping[str, Any],
        *,
        inventory: WorldComponentInventory,
    ) -> DivergenceOracleSpec:
        _require_exact_keys(payload, _ORACLE_KEYS, "divergence_oracle")
        if payload["schema_version"] != DIVERGENCE_ORACLE_SCHEMA_VERSION:
            raise DivergenceOracleError("unsupported divergence oracle schema")
        raw_expectations = payload["expectations"]
        if not isinstance(raw_expectations, list) or not all(
            isinstance(item, Mapping) for item in raw_expectations
        ):
            raise DivergenceOracleError("expectations must be a list of objects")
        oracle = cls(
            oracle_id=str(payload["oracle_id"]),
            intervention_class=cast(InterventionClass, str(payload["intervention_class"])),
            target_component_id=str(payload["target_component_id"]),
            expectations=tuple(DivergenceExpectation.from_dict(item) for item in raw_expectations),
        )
        oracle.validate(inventory)
        return oracle

    def validate(self, inventory: WorldComponentInventory) -> None:
        if self.intervention_class not in ALLOWED_INTERVENTION_CLASSES:
            raise DivergenceOracleError("unsupported intervention_class")
        target = inventory.component_by_id.get(self.target_component_id)
        if target is None or target.fork_policy != "intervention_target":
            raise DivergenceOracleError("target_component_id is not an intervention target")
        if self.intervention_class not in target.allowed_intervention_classes:
            raise DivergenceOracleError("intervention class is incompatible with target component")
        if not self.expectations:
            raise DivergenceOracleError("divergence oracle must declare expectations")
        expectation_ids = tuple(item.expectation_id for item in self.expectations)
        if len(expectation_ids) != len(set(expectation_ids)):
            raise DivergenceOracleError("expectation_id values must be unique")
        channels = {item.channel for item in self.expectations}
        if channels != {"physical_state", "public_observation"}:
            raise DivergenceOracleError(
                "oracle must include physical_state and public_observation expectations"
            )
        if self.oracle_id != self.expected_oracle_id:
            raise DivergenceOracleError("oracle_id does not match oracle content")

    def _core_dict(self) -> dict[str, Any]:
        return {
            "schema_version": DIVERGENCE_ORACLE_SCHEMA_VERSION,
            "intervention_class": self.intervention_class,
            "target_component_id": self.target_component_id,
            "expectations": [item.to_dict() for item in self.expectations],
        }

    @property
    def content_sha256(self) -> str:
        return canonical_json_sha256(self._core_dict())

    @property
    def expected_oracle_id(self) -> str:
        return f"chemworld-divergence-{self.content_sha256[:16]}"

    def to_dict(self) -> dict[str, Any]:
        return {**self._core_dict(), "oracle_id": self.oracle_id}


@dataclass(frozen=True)
class DivergenceExpectationResult:
    expectation_id: str
    channel: DivergenceChannel
    checkpoint_id: str
    field_path: tuple[str, ...]
    parent_value: float | None
    child_value: float | None
    signed_delta: float | None
    absolute_delta: float | None
    relative_delta: float | None
    magnitude_passed: bool
    direction_passed: bool
    passed: bool
    failure_code: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "expectation_id": self.expectation_id,
            "channel": self.channel,
            "checkpoint_id": self.checkpoint_id,
            "field_path": list(self.field_path),
            "parent_value": self.parent_value,
            "child_value": self.child_value,
            "signed_delta": self.signed_delta,
            "absolute_delta": self.absolute_delta,
            "relative_delta": self.relative_delta,
            "magnitude_passed": self.magnitude_passed,
            "direction_passed": self.direction_passed,
            "passed": self.passed,
            "failure_code": self.failure_code,
        }


def _resolve_numeric(
    checkpoints: Mapping[str, Any],
    expectation: DivergenceExpectation,
) -> tuple[float | None, str | None]:
    value: Any = checkpoints
    path = (expectation.checkpoint_id, expectation.channel, *expectation.field_path)
    for segment in path:
        if not isinstance(value, Mapping) or segment not in value:
            return None, "missing_checkpoint_or_field"
        value = value[segment]
    if isinstance(value, bool):
        return None, "nonnumeric_value"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None, "nonnumeric_value"
    if not math.isfinite(number):
        return None, "nonfinite_value"
    return number, None


def _evaluate_expectation(
    expectation: DivergenceExpectation,
    *,
    parent_checkpoints: Mapping[str, Any],
    child_checkpoints: Mapping[str, Any],
) -> DivergenceExpectationResult:
    parent_value, parent_failure = _resolve_numeric(parent_checkpoints, expectation)
    child_value, child_failure = _resolve_numeric(child_checkpoints, expectation)
    failure = parent_failure or child_failure
    if failure is not None or parent_value is None or child_value is None:
        return DivergenceExpectationResult(
            expectation_id=expectation.expectation_id,
            channel=expectation.channel,
            checkpoint_id=expectation.checkpoint_id,
            field_path=expectation.field_path,
            parent_value=parent_value,
            child_value=child_value,
            signed_delta=None,
            absolute_delta=None,
            relative_delta=None,
            magnitude_passed=False,
            direction_passed=False,
            passed=False,
            failure_code=failure or "unresolved_value",
        )
    signed_delta = child_value - parent_value
    absolute_delta = abs(signed_delta)
    relative_scale = max(abs(parent_value), abs(child_value), expectation.relative_scale_floor)
    relative_delta = absolute_delta / relative_scale
    magnitude_passed = (
        absolute_delta >= expectation.minimum_absolute_delta
        and relative_delta >= expectation.minimum_relative_delta
    )
    direction_passed = (
        expectation.direction == "either"
        or (expectation.direction == "increase" and signed_delta > 0.0)
        or (expectation.direction == "decrease" and signed_delta < 0.0)
    )
    passed = magnitude_passed and direction_passed
    return DivergenceExpectationResult(
        expectation_id=expectation.expectation_id,
        channel=expectation.channel,
        checkpoint_id=expectation.checkpoint_id,
        field_path=expectation.field_path,
        parent_value=parent_value,
        child_value=child_value,
        signed_delta=signed_delta,
        absolute_delta=absolute_delta,
        relative_delta=relative_delta,
        magnitude_passed=magnitude_passed,
        direction_passed=direction_passed,
        passed=passed,
        failure_code=None if passed else "divergence_tolerance_not_met",
    )


def evaluate_divergence_oracle(
    *,
    oracle: DivergenceOracleSpec,
    spec: WorldForkSpec,
    inventory: WorldComponentInventory,
    parent_checkpoints: Mapping[str, Any],
    child_checkpoints: Mapping[str, Any],
) -> dict[str, Any]:
    """Evaluate aligned parent-child checkpoints without executing either world."""

    oracle.validate(inventory)
    spec.validate(inventory)
    if oracle.intervention_class != spec.intervention_class:
        raise DivergenceOracleError("oracle intervention class does not match fork")
    if oracle.target_component_id != spec.target_component_id:
        raise DivergenceOracleError("oracle target component does not match fork")
    results = tuple(
        _evaluate_expectation(
            expectation,
            parent_checkpoints=parent_checkpoints,
            child_checkpoints=child_checkpoints,
        )
        for expectation in oracle.expectations
    )
    physical = tuple(result for result in results if result.channel == "physical_state")
    observations = tuple(result for result in results if result.channel == "public_observation")
    passed = all(result.passed for result in results)
    return {
        "report_version": "chemworld-world-fork-divergence-evaluation-0.1",
        "oracle_id": oracle.oracle_id,
        "oracle_sha256": oracle.content_sha256,
        "fork_id": spec.fork_id,
        "fork_spec_sha256": spec.content_sha256,
        "intervention_class": spec.intervention_class,
        "target_component_id": spec.target_component_id,
        "expectation_results": [result.to_dict() for result in results],
        "physical_expectation_count": len(physical),
        "physical_expectation_pass_count": sum(result.passed for result in physical),
        "observation_expectation_count": len(observations),
        "observation_expectation_pass_count": sum(result.passed for result in observations),
        "passed": passed,
        "claim_boundary": {
            "expected_response_divergence": True,
            "runtime_execution_claim": False,
            "exact_replay_claim": False,
            "agent_performance_claim": False,
        },
    }


__all__ = [
    "DIVERGENCE_ORACLE_SCHEMA_VERSION",
    "DivergenceExpectation",
    "DivergenceExpectationResult",
    "DivergenceOracleError",
    "DivergenceOracleSpec",
    "evaluate_divergence_oracle",
]
