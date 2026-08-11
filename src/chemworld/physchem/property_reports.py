"""Shared property report contracts for ChemWorld property models."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from math import isfinite
from typing import Literal

from chemworld.foundation.units import Quantity, convert_value

R_J_PER_MOL_K = 8.31446261815324
STANDARD_PRESSURE_PA = 101325.0
ValidityPolicy = Literal["warn", "raise", "ignore"]
PhaseLabel = Literal["solid", "liquid", "gas"]
_PHASES = {"solid", "liquid", "gas"}


@dataclass(frozen=True)
class PropertyEvaluation:
    property_id: str
    correlation_id: str
    equation_id: str
    value: float
    unit: str
    inputs: dict[str, float]
    warnings: tuple[str, ...] = ()

    @property
    def valid(self) -> bool:
        return not self.warnings

    def quantity(self) -> Quantity:
        return Quantity(self.value, self.unit)

    def to(self, target_unit: str) -> PropertyEvaluation:
        return PropertyEvaluation(
            property_id=self.property_id,
            correlation_id=self.correlation_id,
            equation_id=self.equation_id,
            value=convert_value(self.value, self.unit, target_unit),
            unit=target_unit,
            inputs=dict(self.inputs),
            warnings=self.warnings,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "property_id": self.property_id,
            "correlation_id": self.correlation_id,
            "equation_id": self.equation_id,
            "value": self.value,
            "unit": self.unit,
            "inputs": dict(self.inputs),
            "warnings": list(self.warnings),
            "valid": self.valid,
        }


def _validate_phase(phase: str) -> None:
    if phase not in _PHASES:
        raise ValueError(f"Unsupported phase {phase!r}; expected one of {sorted(_PHASES)}")


def _pressure_unit_to_pa_factor(unit: str) -> float:
    return convert_value(1.0, unit, "Pa")


def _validated_fraction_mapping(
    fractions: Mapping[str, float],
    fraction_name: str,
) -> dict[str, float]:
    if not fractions:
        raise ValueError(f"component_{fraction_name}_fractions cannot be empty")
    total = sum(fractions.values())
    if abs(total - 1.0) > 1e-9:
        raise ValueError(f"component {fraction_name} fractions must sum to 1")
    normalized: dict[str, float] = {}
    for component_id, fraction in fractions.items():
        if not component_id:
            raise ValueError("component id cannot be empty")
        if fraction < 0 or not isfinite(fraction):
            raise ValueError(f"invalid {fraction_name} fraction for {component_id!r}")
        normalized[component_id] = float(fraction)
    return normalized


def _require_same_keys(
    reference: Mapping[str, float],
    values: Mapping[str, float],
    value_name: str,
) -> None:
    missing = sorted(set(reference) - set(values))
    extra = sorted(set(values) - set(reference))
    if missing or extra:
        raise ValueError(
            f"{value_name} keys must match components; missing={missing}, extra={extra}"
        )


def _clamp(value: float, lower: float, upper: float) -> float:
    return min(max(value, lower), upper)

