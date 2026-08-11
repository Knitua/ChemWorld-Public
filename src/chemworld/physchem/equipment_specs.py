"""Serializable equipment cards and operating-constraint evaluation."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from math import isfinite
from typing import Literal, cast

EquipmentType = Literal[
    "vessel",
    "pump",
    "mixer",
    "condenser",
    "heat_exchanger",
    "column",
]
ConstraintRelation = Literal["minimum", "maximum"]
ConstraintSeverity = Literal["warning", "hard"]


@dataclass(frozen=True)
class EquipmentConstraintSpec:
    constraint_id: str
    field_name: str
    relation: ConstraintRelation
    limit: float
    unit: str
    severity: ConstraintSeverity = "hard"

    def __post_init__(self) -> None:
        if not self.constraint_id or not self.field_name or not self.unit:
            raise ValueError("constraint id, field name, and unit cannot be empty")
        if self.relation not in {"minimum", "maximum"}:
            raise ValueError("constraint relation must be minimum or maximum")
        if self.severity not in {"warning", "hard"}:
            raise ValueError("constraint severity must be warning or hard")
        if not isfinite(self.limit):
            raise ValueError("constraint limit must be finite")

    def to_dict(self) -> dict[str, object]:
        return {
            "constraint_id": self.constraint_id,
            "field_name": self.field_name,
            "relation": self.relation,
            "limit": self.limit,
            "unit": self.unit,
            "severity": self.severity,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> EquipmentConstraintSpec:
        return cls(
            constraint_id=str(payload["constraint_id"]),
            field_name=str(payload["field_name"]),
            relation=cast(ConstraintRelation, str(payload["relation"])),
            limit=_as_float(payload["limit"], "constraint limit"),
            unit=str(payload["unit"]),
            severity=cast(
                ConstraintSeverity,
                str(payload.get("severity", "hard")),
            ),
        )


@dataclass(frozen=True)
class EquipmentCardSpec:
    equipment_id: str
    equipment_type: EquipmentType
    title: str
    parameters: dict[str, float | int | str]
    constraints: tuple[EquipmentConstraintSpec, ...]
    provenance_id: str
    schema_version: str = "chemworld-equipment-card-0.1"
    metadata: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.equipment_id or not self.title or not self.provenance_id:
            raise ValueError("equipment id, title, and provenance cannot be empty")
        if self.equipment_type not in {
            "vessel",
            "pump",
            "mixer",
            "condenser",
            "heat_exchanger",
            "column",
        }:
            raise ValueError("unsupported equipment_type")
        if self.schema_version != "chemworld-equipment-card-0.1":
            raise ValueError("unsupported equipment card schema")
        if not self.constraints:
            raise ValueError("equipment cards require at least one constraint")
        constraint_ids = [item.constraint_id for item in self.constraints]
        if len(constraint_ids) != len(set(constraint_ids)):
            raise ValueError("duplicate equipment constraint ids are not allowed")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "equipment_id": self.equipment_id,
            "equipment_type": self.equipment_type,
            "title": self.title,
            "parameters": dict(self.parameters),
            "constraints": [item.to_dict() for item in self.constraints],
            "provenance_id": self.provenance_id,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> EquipmentCardSpec:
        raw_constraints = payload["constraints"]
        if not isinstance(raw_constraints, list):
            raise ValueError("constraints must be a list")
        raw_parameters = payload["parameters"]
        raw_metadata = payload.get("metadata", {})
        if not isinstance(raw_parameters, dict) or not isinstance(raw_metadata, dict):
            raise ValueError("parameters and metadata must be objects")
        return cls(
            equipment_id=str(payload["equipment_id"]),
            equipment_type=cast(EquipmentType, str(payload["equipment_type"])),
            title=str(payload["title"]),
            parameters={str(key): _card_scalar(value) for key, value in raw_parameters.items()},
            constraints=tuple(
                EquipmentConstraintSpec.from_dict(item)
                for item in raw_constraints
                if isinstance(item, dict)
            ),
            provenance_id=str(payload["provenance_id"]),
            schema_version=str(payload["schema_version"]),
            metadata={str(key): value for key, value in raw_metadata.items()},
        )


@dataclass(frozen=True)
class EquipmentConstraintCheck:
    constraint_id: str
    field_name: str
    value: float
    limit: float
    relation: ConstraintRelation
    unit: str
    severity: ConstraintSeverity
    margin: float
    normalized_margin: float
    utilization: float
    violated: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "constraint_id": self.constraint_id,
            "field_name": self.field_name,
            "value": self.value,
            "limit": self.limit,
            "relation": self.relation,
            "unit": self.unit,
            "severity": self.severity,
            "margin": self.margin,
            "normalized_margin": self.normalized_margin,
            "utilization": self.utilization,
            "violated": self.violated,
        }


@dataclass(frozen=True)
class EquipmentConstraintReport:
    equipment_id: str
    equipment_type: EquipmentType
    feasible: bool
    checks: tuple[EquipmentConstraintCheck, ...]
    warning_ids: tuple[str, ...]
    hard_violation_ids: tuple[str, ...]
    maximum_utilization: float

    def to_dict(self) -> dict[str, object]:
        return {
            "equipment_id": self.equipment_id,
            "equipment_type": self.equipment_type,
            "feasible": self.feasible,
            "checks": [item.to_dict() for item in self.checks],
            "warning_ids": list(self.warning_ids),
            "hard_violation_ids": list(self.hard_violation_ids),
            "maximum_utilization": self.maximum_utilization,
        }


def evaluate_equipment_constraints(
    card: EquipmentCardSpec,
    operating_values: Mapping[str, float],
) -> EquipmentConstraintReport:
    checks: list[EquipmentConstraintCheck] = []
    for constraint in card.constraints:
        if constraint.field_name not in operating_values:
            raise ValueError(
                f"operating_values is missing {constraint.field_name!r} for "
                f"constraint {constraint.constraint_id!r}"
            )
        value = float(operating_values[constraint.field_name])
        if not isfinite(value):
            raise ValueError("operating values must be finite")
        if constraint.relation == "maximum":
            margin = constraint.limit - value
            utilization = value / constraint.limit if constraint.limit != 0.0 else 0.0
        else:
            margin = value - constraint.limit
            utilization = (
                constraint.limit / value
                if value != 0.0
                else (0.0 if constraint.limit <= 0.0 else 1.0e12)
            )
        checks.append(
            EquipmentConstraintCheck(
                constraint_id=constraint.constraint_id,
                field_name=constraint.field_name,
                value=value,
                limit=constraint.limit,
                relation=constraint.relation,
                unit=constraint.unit,
                severity=constraint.severity,
                margin=margin,
                normalized_margin=margin / max(abs(constraint.limit), 1.0e-12),
                utilization=utilization,
                violated=margin < 0.0,
            )
        )
    warning_ids = tuple(
        item.constraint_id for item in checks if item.violated and item.severity == "warning"
    )
    hard_ids = tuple(
        item.constraint_id for item in checks if item.violated and item.severity == "hard"
    )
    return EquipmentConstraintReport(
        equipment_id=card.equipment_id,
        equipment_type=card.equipment_type,
        feasible=not hard_ids,
        checks=tuple(checks),
        warning_ids=warning_ids,
        hard_violation_ids=hard_ids,
        maximum_utilization=max((item.utilization for item in checks), default=0.0),
    )


def vessel_equipment_card(
    *,
    equipment_id: str,
    total_volume_m3: float,
    maximum_working_fraction: float,
    design_pressure_Pa: float,
    design_temperature_K: float,
    heat_transfer_area_m2: float,
    provenance_id: str,
) -> EquipmentCardSpec:
    _positive(total_volume_m3, "total_volume_m3")
    _fraction(maximum_working_fraction, "maximum_working_fraction")
    _positive(design_pressure_Pa, "design_pressure_Pa")
    _positive(design_temperature_K, "design_temperature_K")
    _nonnegative(heat_transfer_area_m2, "heat_transfer_area_m2")
    return EquipmentCardSpec(
        equipment_id=equipment_id,
        equipment_type="vessel",
        title="Process Vessel",
        parameters={
            "total_volume_m3": total_volume_m3,
            "maximum_working_fraction": maximum_working_fraction,
            "heat_transfer_area_m2": heat_transfer_area_m2,
        },
        constraints=(
            _maximum(
                "working_volume",
                "liquid_volume_m3",
                total_volume_m3 * maximum_working_fraction,
                "m^3",
            ),
            _maximum("design_pressure", "pressure_Pa", design_pressure_Pa, "Pa"),
            _maximum("design_temperature", "temperature_K", design_temperature_K, "K"),
        ),
        provenance_id=provenance_id,
    )


def pump_equipment_card(
    *,
    equipment_id: str,
    maximum_flow_m3_s: float,
    maximum_differential_pressure_Pa: float,
    minimum_npsh_margin_m: float,
    rated_efficiency: float,
    provenance_id: str,
) -> EquipmentCardSpec:
    _positive(maximum_flow_m3_s, "maximum_flow_m3_s")
    _positive(maximum_differential_pressure_Pa, "maximum_differential_pressure_Pa")
    _nonnegative(minimum_npsh_margin_m, "minimum_npsh_margin_m")
    _fraction(rated_efficiency, "rated_efficiency")
    return EquipmentCardSpec(
        equipment_id=equipment_id,
        equipment_type="pump",
        title="Process Pump",
        parameters={"rated_efficiency": rated_efficiency},
        constraints=(
            _maximum("maximum_flow", "volumetric_flow_m3_s", maximum_flow_m3_s, "m^3/s"),
            _maximum(
                "maximum_differential_pressure",
                "differential_pressure_Pa",
                maximum_differential_pressure_Pa,
                "Pa",
            ),
            _minimum("npsh_margin", "npsh_margin_m", minimum_npsh_margin_m, "m"),
        ),
        provenance_id=provenance_id,
    )


def mixer_equipment_card(
    *,
    equipment_id: str,
    minimum_liquid_volume_m3: float,
    maximum_liquid_volume_m3: float,
    maximum_rotational_speed_rev_s: float,
    maximum_power_W: float,
    maximum_power_density_W_m3: float,
    impeller_diameter_m: float,
    provenance_id: str,
) -> EquipmentCardSpec:
    for name, value in (
        ("minimum_liquid_volume_m3", minimum_liquid_volume_m3),
        ("maximum_liquid_volume_m3", maximum_liquid_volume_m3),
        ("maximum_rotational_speed_rev_s", maximum_rotational_speed_rev_s),
        ("maximum_power_W", maximum_power_W),
        ("maximum_power_density_W_m3", maximum_power_density_W_m3),
        ("impeller_diameter_m", impeller_diameter_m),
    ):
        _positive(value, name)
    if minimum_liquid_volume_m3 >= maximum_liquid_volume_m3:
        raise ValueError("mixer liquid-volume range must be increasing")
    return EquipmentCardSpec(
        equipment_id=equipment_id,
        equipment_type="mixer",
        title="Agitated Mixer",
        parameters={"impeller_diameter_m": impeller_diameter_m},
        constraints=(
            _minimum("minimum_liquid_volume", "liquid_volume_m3", minimum_liquid_volume_m3, "m^3"),
            _maximum("maximum_liquid_volume", "liquid_volume_m3", maximum_liquid_volume_m3, "m^3"),
            _maximum(
                "maximum_rotational_speed",
                "rotational_speed_rev_s",
                maximum_rotational_speed_rev_s,
                "1/s",
            ),
            _maximum("maximum_power", "power_W", maximum_power_W, "W"),
            _maximum(
                "maximum_power_density",
                "power_density_W_m3",
                maximum_power_density_W_m3,
                "W/m^3",
                severity="warning",
            ),
        ),
        provenance_id=provenance_id,
    )


def condenser_equipment_card(
    *,
    equipment_id: str,
    heat_transfer_area_m2: float,
    overall_u_W_m2_K: float,
    maximum_duty_W: float,
    design_pressure_Pa: float,
    maximum_process_temperature_K: float,
    provenance_id: str,
) -> EquipmentCardSpec:
    return _thermal_equipment_card(
        equipment_id=equipment_id,
        equipment_type="condenser",
        title="Condenser",
        heat_transfer_area_m2=heat_transfer_area_m2,
        overall_u_W_m2_K=overall_u_W_m2_K,
        maximum_duty_W=maximum_duty_W,
        design_pressure_Pa=design_pressure_Pa,
        maximum_process_temperature_K=maximum_process_temperature_K,
        provenance_id=provenance_id,
    )


def heat_exchanger_equipment_card(
    *,
    equipment_id: str,
    heat_transfer_area_m2: float,
    overall_u_W_m2_K: float,
    maximum_duty_W: float,
    design_pressure_Pa: float,
    maximum_process_temperature_K: float,
    lmtd_correction_factor: float,
    provenance_id: str,
) -> EquipmentCardSpec:
    _fraction(lmtd_correction_factor, "lmtd_correction_factor")
    card = _thermal_equipment_card(
        equipment_id=equipment_id,
        equipment_type="heat_exchanger",
        title="Heat Exchanger",
        heat_transfer_area_m2=heat_transfer_area_m2,
        overall_u_W_m2_K=overall_u_W_m2_K,
        maximum_duty_W=maximum_duty_W,
        design_pressure_Pa=design_pressure_Pa,
        maximum_process_temperature_K=maximum_process_temperature_K,
        provenance_id=provenance_id,
    )
    return EquipmentCardSpec(
        equipment_id=card.equipment_id,
        equipment_type=card.equipment_type,
        title=card.title,
        parameters={**card.parameters, "lmtd_correction_factor": lmtd_correction_factor},
        constraints=card.constraints,
        provenance_id=card.provenance_id,
    )


def column_equipment_card(
    *,
    equipment_id: str,
    diameter_m: float,
    height_m: float,
    stage_count: int,
    maximum_flood_fraction: float,
    design_pressure_Pa: float,
    design_temperature_K: float,
    maximum_reboiler_duty_W: float,
    maximum_condenser_duty_W: float,
    provenance_id: str,
) -> EquipmentCardSpec:
    for name, value in (
        ("diameter_m", diameter_m),
        ("height_m", height_m),
        ("design_pressure_Pa", design_pressure_Pa),
        ("design_temperature_K", design_temperature_K),
        ("maximum_reboiler_duty_W", maximum_reboiler_duty_W),
        ("maximum_condenser_duty_W", maximum_condenser_duty_W),
    ):
        _positive(value, name)
    if stage_count <= 0:
        raise ValueError("stage_count must be positive")
    _fraction(maximum_flood_fraction, "maximum_flood_fraction")
    return EquipmentCardSpec(
        equipment_id=equipment_id,
        equipment_type="column",
        title="Staged Separation Column",
        parameters={"diameter_m": diameter_m, "height_m": height_m, "stage_count": stage_count},
        constraints=(
            _maximum(
                "flood_fraction",
                "flood_fraction",
                maximum_flood_fraction,
                "dimensionless",
                severity="warning",
            ),
            _maximum("design_pressure", "pressure_Pa", design_pressure_Pa, "Pa"),
            _maximum("design_temperature", "temperature_K", design_temperature_K, "K"),
            _maximum("maximum_reboiler_duty", "reboiler_duty_W", maximum_reboiler_duty_W, "W"),
            _maximum("maximum_condenser_duty", "condenser_duty_W", maximum_condenser_duty_W, "W"),
        ),
        provenance_id=provenance_id,
    )


def _thermal_equipment_card(
    *,
    equipment_id: str,
    equipment_type: EquipmentType,
    title: str,
    heat_transfer_area_m2: float,
    overall_u_W_m2_K: float,
    maximum_duty_W: float,
    design_pressure_Pa: float,
    maximum_process_temperature_K: float,
    provenance_id: str,
) -> EquipmentCardSpec:
    for name, value in (
        ("heat_transfer_area_m2", heat_transfer_area_m2),
        ("overall_u_W_m2_K", overall_u_W_m2_K),
        ("maximum_duty_W", maximum_duty_W),
        ("design_pressure_Pa", design_pressure_Pa),
        ("maximum_process_temperature_K", maximum_process_temperature_K),
    ):
        _positive(value, name)
    return EquipmentCardSpec(
        equipment_id=equipment_id,
        equipment_type=equipment_type,
        title=title,
        parameters={
            "heat_transfer_area_m2": heat_transfer_area_m2,
            "overall_u_W_m2_K": overall_u_W_m2_K,
        },
        constraints=(
            _maximum("maximum_duty", "duty_W", maximum_duty_W, "W"),
            _maximum("design_pressure", "pressure_Pa", design_pressure_Pa, "Pa"),
            _maximum(
                "maximum_process_temperature",
                "process_temperature_K",
                maximum_process_temperature_K,
                "K",
            ),
        ),
        provenance_id=provenance_id,
    )


def _minimum(
    constraint_id: str,
    field_name: str,
    limit: float,
    unit: str,
    *,
    severity: ConstraintSeverity = "hard",
) -> EquipmentConstraintSpec:
    return EquipmentConstraintSpec(constraint_id, field_name, "minimum", limit, unit, severity)


def _maximum(
    constraint_id: str,
    field_name: str,
    limit: float,
    unit: str,
    *,
    severity: ConstraintSeverity = "hard",
) -> EquipmentConstraintSpec:
    return EquipmentConstraintSpec(constraint_id, field_name, "maximum", limit, unit, severity)


def _card_scalar(value: object) -> float | int | str:
    if isinstance(value, bool):
        raise ValueError("equipment parameter values cannot be boolean")
    if isinstance(value, (float, int, str)):
        return value
    raise ValueError("equipment parameter values must be float, int, or str")


def _as_float(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (float, int)):
        raise ValueError(f"{field_name} must be numeric")
    return float(value)


def _positive(value: float, field_name: str) -> None:
    if value <= 0.0 or not isfinite(value):
        raise ValueError(f"{field_name} must be positive and finite")


def _nonnegative(value: float, field_name: str) -> None:
    if value < 0.0 or not isfinite(value):
        raise ValueError(f"{field_name} must be nonnegative and finite")


def _fraction(value: float, field_name: str) -> None:
    if not 0.0 < value <= 1.0 or not isfinite(value):
        raise ValueError(f"{field_name} must be finite and in (0, 1]")


__all__ = [
    "EquipmentCardSpec",
    "EquipmentConstraintCheck",
    "EquipmentConstraintReport",
    "EquipmentConstraintSpec",
    "column_equipment_card",
    "condenser_equipment_card",
    "evaluate_equipment_constraints",
    "heat_exchanger_equipment_card",
    "mixer_equipment_card",
    "pump_equipment_card",
    "vessel_equipment_card",
]
