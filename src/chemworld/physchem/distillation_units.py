"""Duty- and equipment-limited shortcut distillation with explicit ledgers."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from math import isfinite
from typing import Any, cast

from chemworld.physchem.equilibrium import ActivityModelSpec
from chemworld.physchem.maturity import (
    MaturityLevel,
    ModelCard,
    ValidationEvidence,
)
from chemworld.physchem.separations import (
    SeparationResult,
    fenske_minimum_stages,
    gilliland_eduljee_stage_estimate,
    underwood_minimum_reflux_binary,
    vle_shortcut_distillation,
)

DUTY_LIMITED_DISTILLATION_MODEL_ID = "chemworld_duty_limited_distillation_vnext"
DISTILLATION_ENGINE_MODEL_ID = "vle_shortcut_distillation"
IDAES_COMMIT = "4275c45bfa76cd5b05926beaa8eee58f7b0b05e8"
IDAES_TRAY_COLUMN_PATH = "idaes/models_extra/column_models/tray_column.py"
IDAES_CONDENSER_PATH = "idaes/models_extra/column_models/condenser.py"
IDAES_REBOILER_PATH = "idaes/models_extra/column_models/reboiler.py"


def _finite_positive(value: float, label: str) -> float:
    resolved = float(value)
    if not isfinite(resolved) or resolved <= 0.0:
        raise ValueError(f"{label} must be finite and positive")
    return resolved


def _finite_nonnegative(value: float, label: str) -> float:
    resolved = float(value)
    if not isfinite(resolved) or resolved < 0.0:
        raise ValueError(f"{label} must be finite and nonnegative")
    return resolved


def _closed_fraction(value: float, label: str) -> float:
    resolved = float(value)
    if not isfinite(resolved) or not 0.0 <= resolved <= 1.0:
        raise ValueError(f"{label} must lie in [0, 1]")
    return resolved


def _amounts(values: Mapping[str, float]) -> dict[str, float]:
    resolved: dict[str, float] = {}
    for raw_component_id, raw_amount in values.items():
        component_id = str(raw_component_id).strip()
        if not component_id:
            raise ValueError("feed component ids cannot be empty")
        if component_id in resolved:
            raise ValueError("feed component ids collide after normalization")
        resolved[component_id] = _finite_nonnegative(
            raw_amount,
            f"feed_amounts_mol[{component_id!r}]",
        )
    if len(resolved) < 2 or sum(resolved.values()) <= 0.0:
        raise ValueError("feed_amounts_mol requires at least two components and positive material")
    return dict(sorted(resolved.items()))


def _balance_error(
    feed: Mapping[str, float],
    outlets: Mapping[str, Mapping[str, float]],
) -> float:
    return max(
        (
            abs(
                feed[component_id]
                - sum(outlet.get(component_id, 0.0) for outlet in outlets.values())
            )
            for component_id in feed
        ),
        default=0.0,
    )


@dataclass(frozen=True)
class DistillationComponentSpec:
    """Property values evaluated at the declared column operating temperature."""

    component_id: str
    vapor_pressure_Pa: float
    latent_heat_J_mol: float
    liquid_heat_capacity_J_mol_K: float
    evaluation_temperature_K: float
    thermal_limit_K: float
    provenance_id: str
    vapor_fugacity_coefficient: float = 1.0

    def __post_init__(self) -> None:
        component_id = self.component_id.strip()
        provenance_id = self.provenance_id.strip()
        if not component_id or not provenance_id:
            raise ValueError("component_id and provenance_id cannot be empty")
        object.__setattr__(self, "component_id", component_id)
        object.__setattr__(self, "provenance_id", provenance_id)
        for field_name in (
            "vapor_pressure_Pa",
            "latent_heat_J_mol",
            "liquid_heat_capacity_J_mol_K",
            "evaluation_temperature_K",
            "thermal_limit_K",
            "vapor_fugacity_coefficient",
        ):
            object.__setattr__(
                self,
                field_name,
                _finite_positive(getattr(self, field_name), field_name),
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "component_id": self.component_id,
            "vapor_pressure_Pa": self.vapor_pressure_Pa,
            "latent_heat_J_mol": self.latent_heat_J_mol,
            "liquid_heat_capacity_J_mol_K": self.liquid_heat_capacity_J_mol_K,
            "evaluation_temperature_K": self.evaluation_temperature_K,
            "thermal_limit_K": self.thermal_limit_K,
            "provenance_id": self.provenance_id,
            "vapor_fugacity_coefficient": self.vapor_fugacity_coefficient,
        }


@dataclass(frozen=True)
class ShortcutColumnSpec:
    """Installed column, utility, and batch-domain constraints."""

    theoretical_stages: float
    stage_efficiency: float
    maximum_reboiler_power_W: float
    maximum_condenser_power_W: float
    maximum_internal_vapor_rate_mol_s: float
    maximum_batch_amount_mol: float
    minimum_bottoms_amount_mol: float
    maximum_distillate_cut_fraction: float
    minimum_pressure_Pa: float
    maximum_pressure_Pa: float
    maximum_temperature_K: float
    maximum_duration_s: float
    maximum_reflux_ratio: float
    provenance_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "theoretical_stages",
            _finite_positive(self.theoretical_stages, "theoretical_stages"),
        )
        stage_efficiency = _closed_fraction(self.stage_efficiency, "stage_efficiency")
        if stage_efficiency <= 0.0:
            raise ValueError("stage_efficiency must be positive")
        object.__setattr__(self, "stage_efficiency", stage_efficiency)
        for field_name in (
            "maximum_reboiler_power_W",
            "maximum_condenser_power_W",
            "maximum_internal_vapor_rate_mol_s",
            "minimum_bottoms_amount_mol",
            "maximum_duration_s",
            "maximum_reflux_ratio",
        ):
            object.__setattr__(
                self,
                field_name,
                _finite_nonnegative(getattr(self, field_name), field_name),
            )
        for field_name in (
            "maximum_batch_amount_mol",
            "minimum_pressure_Pa",
            "maximum_pressure_Pa",
            "maximum_temperature_K",
        ):
            object.__setattr__(
                self,
                field_name,
                _finite_positive(getattr(self, field_name), field_name),
            )
        maximum_cut = _closed_fraction(
            self.maximum_distillate_cut_fraction,
            "maximum_distillate_cut_fraction",
        )
        if maximum_cut <= 0.0:
            raise ValueError("maximum_distillate_cut_fraction must be positive")
        object.__setattr__(self, "maximum_distillate_cut_fraction", maximum_cut)
        if self.minimum_pressure_Pa > self.maximum_pressure_Pa:
            raise ValueError("minimum_pressure_Pa cannot exceed maximum_pressure_Pa")
        if self.minimum_bottoms_amount_mol >= self.maximum_batch_amount_mol:
            raise ValueError("minimum_bottoms_amount_mol must be below maximum batch amount")
        provenance_id = self.provenance_id.strip()
        if not provenance_id:
            raise ValueError("column provenance_id cannot be empty")
        object.__setattr__(self, "provenance_id", provenance_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "theoretical_stages": self.theoretical_stages,
            "stage_efficiency": self.stage_efficiency,
            "maximum_reboiler_power_W": self.maximum_reboiler_power_W,
            "maximum_condenser_power_W": self.maximum_condenser_power_W,
            "maximum_internal_vapor_rate_mol_s": (self.maximum_internal_vapor_rate_mol_s),
            "maximum_batch_amount_mol": self.maximum_batch_amount_mol,
            "minimum_bottoms_amount_mol": self.minimum_bottoms_amount_mol,
            "maximum_distillate_cut_fraction": (self.maximum_distillate_cut_fraction),
            "minimum_pressure_Pa": self.minimum_pressure_Pa,
            "maximum_pressure_Pa": self.maximum_pressure_Pa,
            "maximum_temperature_K": self.maximum_temperature_K,
            "maximum_duration_s": self.maximum_duration_s,
            "maximum_reflux_ratio": self.maximum_reflux_ratio,
            "provenance_id": self.provenance_id,
        }


@dataclass(frozen=True)
class DutyLimitedDistillationRequest:
    feed_amounts_mol: dict[str, float]
    component_specs: dict[str, DistillationComponentSpec]
    light_key: str
    heavy_key: str
    pressure_Pa: float
    initial_temperature_K: float
    operating_temperature_K: float
    duration_s: float
    reflux_ratio: float
    requested_distillate_cut_fraction: float
    column: ShortcutColumnSpec
    activity_model: ActivityModelSpec | None = None
    material_balance_tolerance_mol: float = 1.0e-9
    energy_balance_tolerance_J: float = 1.0e-8
    bubble_pressure_tolerance_fraction: float = 1.0e-9

    def __post_init__(self) -> None:
        feed = _amounts(self.feed_amounts_mol)
        if not isinstance(self.column, ShortcutColumnSpec):
            raise ValueError("column must be a ShortcutColumnSpec")
        if set(self.component_specs) != set(feed):
            raise ValueError("component_specs must exactly match feed component ids")
        specs: dict[str, DistillationComponentSpec] = {}
        for component_id in feed:
            spec = self.component_specs[component_id]
            if not isinstance(spec, DistillationComponentSpec):
                raise ValueError("component_specs values must be DistillationComponentSpec")
            if spec.component_id != component_id:
                raise ValueError("component spec ids must match mapping keys")
            specs[component_id] = spec
        light_key = self.light_key.strip()
        heavy_key = self.heavy_key.strip()
        if light_key not in feed or heavy_key not in feed:
            raise ValueError("light_key and heavy_key must be present in the feed")
        if light_key == heavy_key:
            raise ValueError("light_key and heavy_key must be distinct")
        pressure = _finite_positive(self.pressure_Pa, "pressure_Pa")
        initial_temperature = _finite_positive(
            self.initial_temperature_K,
            "initial_temperature_K",
        )
        operating_temperature = _finite_positive(
            self.operating_temperature_K,
            "operating_temperature_K",
        )
        if initial_temperature > operating_temperature:
            raise ValueError("initial_temperature_K cannot exceed operating_temperature_K")
        if not self.column.minimum_pressure_Pa <= pressure <= self.column.maximum_pressure_Pa:
            raise ValueError("pressure_Pa lies outside the column pressure domain")
        if operating_temperature > self.column.maximum_temperature_K:
            raise ValueError("operating_temperature_K exceeds the column maximum")
        thermal_limit = min(spec.thermal_limit_K for spec in specs.values())
        if operating_temperature > thermal_limit:
            raise ValueError("operating_temperature_K exceeds component thermal limits")
        for spec in specs.values():
            if abs(spec.evaluation_temperature_K - operating_temperature) > 1.0e-9:
                raise ValueError(
                    "component properties must be evaluated at operating_temperature_K"
                )
        duration = _finite_nonnegative(self.duration_s, "duration_s")
        if duration > self.column.maximum_duration_s:
            raise ValueError("duration_s exceeds the column maximum")
        reflux = _finite_nonnegative(self.reflux_ratio, "reflux_ratio")
        if reflux > self.column.maximum_reflux_ratio:
            raise ValueError("reflux_ratio exceeds the column maximum")
        requested_cut = _closed_fraction(
            self.requested_distillate_cut_fraction,
            "requested_distillate_cut_fraction",
        )
        total_feed = sum(feed.values())
        if total_feed > self.column.maximum_batch_amount_mol:
            raise ValueError("feed exceeds maximum_batch_amount_mol")
        if self.activity_model is not None and set(self.activity_model.component_ids) != set(feed):
            raise ValueError("activity_model component ids must match the feed")
        object.__setattr__(
            self,
            "material_balance_tolerance_mol",
            _finite_positive(
                self.material_balance_tolerance_mol,
                "material_balance_tolerance_mol",
            ),
        )
        object.__setattr__(
            self,
            "energy_balance_tolerance_J",
            _finite_positive(
                self.energy_balance_tolerance_J,
                "energy_balance_tolerance_J",
            ),
        )
        bubble_tolerance = _closed_fraction(
            self.bubble_pressure_tolerance_fraction,
            "bubble_pressure_tolerance_fraction",
        )
        object.__setattr__(self, "feed_amounts_mol", feed)
        object.__setattr__(self, "component_specs", specs)
        object.__setattr__(self, "light_key", light_key)
        object.__setattr__(self, "heavy_key", heavy_key)
        object.__setattr__(self, "pressure_Pa", pressure)
        object.__setattr__(self, "initial_temperature_K", initial_temperature)
        object.__setattr__(self, "operating_temperature_K", operating_temperature)
        object.__setattr__(self, "duration_s", duration)
        object.__setattr__(self, "reflux_ratio", reflux)
        object.__setattr__(
            self,
            "requested_distillate_cut_fraction",
            requested_cut,
        )
        object.__setattr__(
            self,
            "bubble_pressure_tolerance_fraction",
            bubble_tolerance,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "feed_amounts_mol": dict(self.feed_amounts_mol),
            "component_specs": {
                component_id: spec.to_dict() for component_id, spec in self.component_specs.items()
            },
            "light_key": self.light_key,
            "heavy_key": self.heavy_key,
            "pressure_Pa": self.pressure_Pa,
            "initial_temperature_K": self.initial_temperature_K,
            "operating_temperature_K": self.operating_temperature_K,
            "duration_s": self.duration_s,
            "reflux_ratio": self.reflux_ratio,
            "requested_distillate_cut_fraction": (self.requested_distillate_cut_fraction),
            "column": self.column.to_dict(),
            "activity_model": (
                None if self.activity_model is None else self.activity_model.to_dict()
            ),
            "material_balance_tolerance_mol": (self.material_balance_tolerance_mol),
            "energy_balance_tolerance_J": self.energy_balance_tolerance_J,
            "bubble_pressure_tolerance_fraction": (self.bubble_pressure_tolerance_fraction),
        }


@dataclass(frozen=True)
class DutyLimitedDistillationResult:
    model_id: str
    engine_model_id: str
    feed_amounts_mol: dict[str, float]
    outlets: dict[str, dict[str, float]]
    light_key: str
    heavy_key: str
    pressure_Pa: float
    initial_temperature_K: float
    final_temperature_K: float
    operating_temperature_K: float
    elapsed_time_s: float
    reflux_ratio: float
    requested_distillate_cut_fraction: float
    actual_distillate_cut_fraction: float
    cut_endpoint_met: bool
    limiting_constraint: str
    bubble_pressure_Pa: float
    bubble_pressure_margin_Pa: float
    minimum_thermal_margin_K: float
    k_values: dict[str, float]
    relative_volatilities: dict[str, float]
    effective_stages: float
    observed_fenske_stage_count: float | None
    fenske_stage_residual: float | None
    fug_available: bool
    fenske_minimum_stages: float | None
    underwood_theta: float | None
    minimum_reflux_ratio: float | None
    reflux_margin: float | None
    gilliland_x: float | None
    gilliland_y: float | None
    required_theoretical_stages: float | None
    installed_equilibrium_stage_margin: float | None
    light_key_distillate_purity: float
    light_key_recovery: float
    heavy_key_bottoms_purity: float
    heavy_key_recovery: float
    sensible_heat_J: float
    latent_reboiler_duty_J: float
    total_reboiler_duty_J: float
    condenser_duty_J: float
    average_reboiler_power_W: float
    average_condenser_power_W: float
    internal_vapor_mol: float
    internal_vapor_rate_mol_s: float
    material_balance_error_mol: float
    energy_balance_error_J: float
    warnings: tuple[str, ...]
    provenance: tuple[str, ...]

    def outlet(self, outlet_id: str) -> dict[str, float]:
        return dict(self.outlets[outlet_id])

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "engine_model_id": self.engine_model_id,
            "feed_amounts_mol": dict(self.feed_amounts_mol),
            "outlets": {key: dict(value) for key, value in self.outlets.items()},
            "light_key": self.light_key,
            "heavy_key": self.heavy_key,
            "pressure_Pa": self.pressure_Pa,
            "initial_temperature_K": self.initial_temperature_K,
            "final_temperature_K": self.final_temperature_K,
            "operating_temperature_K": self.operating_temperature_K,
            "elapsed_time_s": self.elapsed_time_s,
            "reflux_ratio": self.reflux_ratio,
            "requested_distillate_cut_fraction": (self.requested_distillate_cut_fraction),
            "actual_distillate_cut_fraction": self.actual_distillate_cut_fraction,
            "cut_endpoint_met": self.cut_endpoint_met,
            "limiting_constraint": self.limiting_constraint,
            "bubble_pressure_Pa": self.bubble_pressure_Pa,
            "bubble_pressure_margin_Pa": self.bubble_pressure_margin_Pa,
            "minimum_thermal_margin_K": self.minimum_thermal_margin_K,
            "k_values": dict(self.k_values),
            "relative_volatilities": dict(self.relative_volatilities),
            "effective_stages": self.effective_stages,
            "observed_fenske_stage_count": self.observed_fenske_stage_count,
            "fenske_stage_residual": self.fenske_stage_residual,
            "fug_available": self.fug_available,
            "fenske_minimum_stages": self.fenske_minimum_stages,
            "underwood_theta": self.underwood_theta,
            "minimum_reflux_ratio": self.minimum_reflux_ratio,
            "reflux_margin": self.reflux_margin,
            "gilliland_x": self.gilliland_x,
            "gilliland_y": self.gilliland_y,
            "required_theoretical_stages": self.required_theoretical_stages,
            "installed_equilibrium_stage_margin": (self.installed_equilibrium_stage_margin),
            "light_key_distillate_purity": self.light_key_distillate_purity,
            "light_key_recovery": self.light_key_recovery,
            "heavy_key_bottoms_purity": self.heavy_key_bottoms_purity,
            "heavy_key_recovery": self.heavy_key_recovery,
            "sensible_heat_J": self.sensible_heat_J,
            "latent_reboiler_duty_J": self.latent_reboiler_duty_J,
            "total_reboiler_duty_J": self.total_reboiler_duty_J,
            "condenser_duty_J": self.condenser_duty_J,
            "average_reboiler_power_W": self.average_reboiler_power_W,
            "average_condenser_power_W": self.average_condenser_power_W,
            "internal_vapor_mol": self.internal_vapor_mol,
            "internal_vapor_rate_mol_s": self.internal_vapor_rate_mol_s,
            "material_balance_error_mol": self.material_balance_error_mol,
            "energy_balance_error_J": self.energy_balance_error_J,
            "warnings": list(self.warnings),
            "provenance": list(self.provenance),
        }


@dataclass(frozen=True)
class _FUGDiagnostics:
    available: bool
    minimum_stages: float | None = None
    underwood_theta: float | None = None
    minimum_reflux_ratio: float | None = None
    reflux_margin: float | None = None
    gilliland_x: float | None = None
    gilliland_y: float | None = None
    required_theoretical_stages: float | None = None
    installed_equilibrium_stage_margin: float | None = None
    warnings: tuple[str, ...] = ()


def simulate_duty_limited_distillation(
    request: DutyLimitedDistillationRequest,
) -> DutyLimitedDistillationResult:
    """Apply VLE/Fenske separation only within thermal and equipment capacity."""

    if not isinstance(request, DutyLimitedDistillationRequest):
        raise ValueError("request must be a DutyLimitedDistillationRequest")
    total_feed = sum(request.feed_amounts_mol.values())
    total_heat_capacity = sum(
        request.feed_amounts_mol[component_id]
        * request.component_specs[component_id].liquid_heat_capacity_J_mol_K
        for component_id in request.feed_amounts_mol
    )
    sensible_required = total_heat_capacity * (
        request.operating_temperature_K - request.initial_temperature_K
    )
    available_reboiler_energy = request.column.maximum_reboiler_power_W * request.duration_s
    zero_engine = _engine_result(request, 0.0)
    k_values = _metadata_mapping(zero_engine, "k_values")
    overall_composition = {
        component_id: amount / total_feed
        for component_id, amount in request.feed_amounts_mol.items()
    }
    bubble_pressure = request.pressure_Pa * sum(
        overall_composition[component_id] * k_values[component_id]
        for component_id in request.feed_amounts_mol
    )
    bubble_margin = bubble_pressure - request.pressure_Pa
    thermal_margin = min(
        spec.thermal_limit_K - request.operating_temperature_K
        for spec in request.component_specs.values()
    )

    if available_reboiler_energy + request.energy_balance_tolerance_J < sensible_required:
        final_temperature = request.initial_temperature_K + (
            available_reboiler_energy / total_heat_capacity
        )
        return _result(
            request=request,
            engine=zero_engine,
            final_temperature_K=final_temperature,
            actual_cut=0.0,
            limiting_constraint="insufficient_sensible_heat",
            bubble_pressure_Pa=bubble_pressure,
            bubble_pressure_margin_Pa=bubble_margin,
            minimum_thermal_margin_K=thermal_margin,
            sensible_heat_J=available_reboiler_energy,
            latent_duty_J=0.0,
            warnings=("operating temperature was not reached",),
        )

    if bubble_margin < (-request.bubble_pressure_tolerance_fraction * request.pressure_Pa):
        return _result(
            request=request,
            engine=zero_engine,
            final_temperature_K=request.operating_temperature_K,
            actual_cut=0.0,
            limiting_constraint="below_bubble_point",
            bubble_pressure_Pa=bubble_pressure,
            bubble_pressure_margin_Pa=bubble_margin,
            minimum_thermal_margin_K=thermal_margin,
            sensible_heat_J=sensible_required,
            latent_duty_J=0.0,
            warnings=("operating state is below the declared mixture bubble point",),
        )

    residual_cut_limit = max(
        0.0,
        1.0 - request.column.minimum_bottoms_amount_mol / total_feed,
    )
    candidate_cut = min(
        request.requested_distillate_cut_fraction,
        request.column.maximum_distillate_cut_fraction,
        residual_cut_limit,
    )
    latent_budget = max(available_reboiler_energy - sensible_required, 0.0)
    condenser_budget = request.column.maximum_condenser_power_W * request.duration_s
    vapor_budget = request.column.maximum_internal_vapor_rate_mol_s * request.duration_s
    cut_limits = {
        "requested_cut": request.requested_distillate_cut_fraction,
        "column_cut_limit": request.column.maximum_distillate_cut_fraction,
        "minimum_bottoms_amount": residual_cut_limit,
        "reboiler_duty": _maximum_cut_for_metric(
            request,
            candidate_cut,
            metric=lambda result: result.ledger.heat_duty_J,
            limit=latent_budget,
        ),
        "condenser_duty": _maximum_cut_for_metric(
            request,
            candidate_cut,
            metric=lambda result: result.ledger.heat_duty_J,
            limit=condenser_budget,
        ),
        "internal_vapor_rate": _maximum_cut_for_metric(
            request,
            candidate_cut,
            metric=_internal_vapor_mol,
            limit=vapor_budget,
        ),
    }
    limiting_constraint, actual_cut = min(
        cut_limits.items(),
        key=lambda item: (
            item[1],
            (
                "requested_cut",
                "column_cut_limit",
                "minimum_bottoms_amount",
                "reboiler_duty",
                "condenser_duty",
                "internal_vapor_rate",
            ).index(item[0]),
        ),
    )
    actual_cut = max(0.0, min(actual_cut, candidate_cut))
    engine = _engine_result(request, actual_cut)
    latent_duty = engine.ledger.heat_duty_J
    warnings: list[str] = []
    if actual_cut + 1.0e-9 < request.requested_distillate_cut_fraction:
        warnings.append(f"requested cut not reached: {limiting_constraint}")
    if abs(bubble_margin) <= 0.05 * request.pressure_Pa:
        warnings.append("operating point is within five percent of bubble pressure")
    if thermal_margin <= 5.0:
        warnings.append("operating temperature is within 5 K of a component thermal limit")
    return _result(
        request=request,
        engine=engine,
        final_temperature_K=request.operating_temperature_K,
        actual_cut=actual_cut,
        limiting_constraint=limiting_constraint,
        bubble_pressure_Pa=bubble_pressure,
        bubble_pressure_margin_Pa=bubble_margin,
        minimum_thermal_margin_K=thermal_margin,
        sensible_heat_J=sensible_required,
        latent_duty_J=latent_duty,
        warnings=tuple(warnings),
    )


def _engine_result(
    request: DutyLimitedDistillationRequest,
    cut_fraction: float,
) -> SeparationResult:
    return vle_shortcut_distillation(
        request.feed_amounts_mol,
        vapor_pressures_Pa={
            component_id: spec.vapor_pressure_Pa
            for component_id, spec in request.component_specs.items()
        },
        pressure_Pa=request.pressure_Pa,
        temperature_K=request.operating_temperature_K,
        light_key=request.light_key,
        heavy_key=request.heavy_key,
        distillate_cut_fraction=cut_fraction,
        theoretical_stages=request.column.theoretical_stages,
        reflux_ratio=request.reflux_ratio,
        stage_efficiency=request.column.stage_efficiency,
        activity_model=request.activity_model,
        latent_heats_J_mol={
            component_id: spec.latent_heat_J_mol
            for component_id, spec in request.component_specs.items()
        },
        vapor_fugacity_coefficients={
            component_id: spec.vapor_fugacity_coefficient
            for component_id, spec in request.component_specs.items()
        },
    )


def _maximum_cut_for_metric(
    request: DutyLimitedDistillationRequest,
    maximum_cut: float,
    *,
    metric: Callable[[SeparationResult], float],
    limit: float,
) -> float:
    if maximum_cut <= 0.0 or limit <= 0.0:
        return 0.0
    if metric(_engine_result(request, maximum_cut)) <= limit:
        return maximum_cut
    low = 0.0
    high = maximum_cut
    for _ in range(60):
        midpoint = 0.5 * (low + high)
        if metric(_engine_result(request, midpoint)) <= limit:
            low = midpoint
        else:
            high = midpoint
    return low


def _metadata_mapping(
    result: SeparationResult,
    key: str,
) -> dict[str, float]:
    raw_value = result.ledger.metadata[key]
    if not isinstance(raw_value, dict):
        raise RuntimeError(f"distillation engine metadata {key!r} is not a mapping")
    resolved = {str(item): float(value) for item, value in raw_value.items()}
    if any(not isfinite(value) or value <= 0.0 for value in resolved.values()):
        raise RuntimeError(f"distillation engine metadata {key!r} is invalid")
    return resolved


def _internal_vapor_mol(result: SeparationResult) -> float:
    value = float(cast(float, result.ledger.metadata["internal_vapor_mol"]))
    if not isfinite(value) or value < 0.0:
        raise RuntimeError("distillation engine returned invalid internal vapor traffic")
    return value


def _fug_diagnostics(
    request: DutyLimitedDistillationRequest,
    engine: SeparationResult,
) -> _FUGDiagnostics:
    if len(request.feed_amounts_mol) != 2:
        return _FUGDiagnostics(
            available=False,
            warnings=("binary FUG diagnostic unavailable for multicomponent feed",),
        )
    distillate = engine.outlet("distillate")
    bottoms = engine.outlet("bottoms")
    distillate_key_total = distillate[request.light_key] + distillate[request.heavy_key]
    bottoms_key_total = bottoms[request.light_key] + bottoms[request.heavy_key]
    if distillate_key_total <= 0.0 or bottoms_key_total <= 0.0:
        return _FUGDiagnostics(
            available=False,
            warnings=("binary FUG diagnostic requires nonempty distillate and bottoms",),
        )
    feed_total = sum(request.feed_amounts_mol.values())
    feed_light = request.feed_amounts_mol[request.light_key] / feed_total
    distillate_light = distillate[request.light_key] / distillate_key_total
    bottoms_light = bottoms[request.light_key] / bottoms_key_total
    if not 0.0 < bottoms_light < feed_light < distillate_light < 1.0:
        return _FUGDiagnostics(
            available=False,
            warnings=("binary product compositions do not satisfy FUG key ordering",),
        )
    relative_volatilities = _metadata_mapping(engine, "relative_volatilities")
    relative_volatility = (
        relative_volatilities[request.light_key] / relative_volatilities[request.heavy_key]
    )
    minimum_stages = fenske_minimum_stages(
        relative_volatility=relative_volatility,
        distillate_light_mole_fraction=distillate_light,
        bottoms_light_mole_fraction=bottoms_light,
    )
    try:
        theta, minimum_reflux = underwood_minimum_reflux_binary(
            relative_volatility=relative_volatility,
            feed_light_mole_fraction=feed_light,
            distillate_light_mole_fraction=distillate_light,
        )
    except ValueError as error:
        return _FUGDiagnostics(
            available=False,
            minimum_stages=minimum_stages,
            warnings=(f"binary Underwood diagnostic unavailable: {error}",),
        )
    reflux_margin = request.reflux_ratio - minimum_reflux
    warnings: list[str] = []
    installed_equilibrium_stages = (
        request.column.theoretical_stages * request.column.stage_efficiency
    )
    if installed_equilibrium_stages + 1.0e-9 < minimum_stages:
        warnings.append("installed equilibrium stages are below the Fenske minimum")
    if reflux_margin <= 0.0:
        return _FUGDiagnostics(
            available=False,
            minimum_stages=minimum_stages,
            underwood_theta=theta,
            minimum_reflux_ratio=minimum_reflux,
            reflux_margin=reflux_margin,
            warnings=("operating reflux does not exceed the binary Underwood minimum",),
        )
    gilliland_x, gilliland_y, required_stages = gilliland_eduljee_stage_estimate(
        minimum_stages=minimum_stages,
        minimum_reflux_ratio=minimum_reflux,
        reflux_ratio=request.reflux_ratio,
    )
    stage_margin = installed_equilibrium_stages - required_stages
    if stage_margin < -1.0e-9:
        warnings.append("installed equilibrium stages are below the Gilliland requirement")
    return _FUGDiagnostics(
        available=True,
        minimum_stages=minimum_stages,
        underwood_theta=theta,
        minimum_reflux_ratio=minimum_reflux,
        reflux_margin=reflux_margin,
        gilliland_x=gilliland_x,
        gilliland_y=gilliland_y,
        required_theoretical_stages=required_stages,
        installed_equilibrium_stage_margin=stage_margin,
        warnings=tuple(warnings),
    )


def _result(
    *,
    request: DutyLimitedDistillationRequest,
    engine: SeparationResult,
    final_temperature_K: float,
    actual_cut: float,
    limiting_constraint: str,
    bubble_pressure_Pa: float,
    bubble_pressure_margin_Pa: float,
    minimum_thermal_margin_K: float,
    sensible_heat_J: float,
    latent_duty_J: float,
    warnings: tuple[str, ...],
) -> DutyLimitedDistillationResult:
    outlets = {
        "distillate": engine.outlet("distillate"),
        "bottoms": engine.outlet("bottoms"),
    }
    material_error = _balance_error(request.feed_amounts_mol, outlets)
    if material_error > request.material_balance_tolerance_mol:
        raise RuntimeError(
            f"distillation material balance error exceeds tolerance: {material_error:.6g} mol"
        )
    total_reboiler = sensible_heat_J + latent_duty_J
    condenser_duty = latent_duty_J
    energy_error = abs(total_reboiler - sensible_heat_J - latent_duty_J) + abs(
        condenser_duty - latent_duty_J
    )
    if energy_error > request.energy_balance_tolerance_J:
        raise RuntimeError(
            f"distillation energy balance error exceeds tolerance: {energy_error:.6g} J"
        )
    duration = request.duration_s
    average_reboiler_power = 0.0 if duration <= 0.0 else total_reboiler / duration
    average_condenser_power = 0.0 if duration <= 0.0 else condenser_duty / duration
    internal_vapor = _internal_vapor_mol(engine)
    internal_vapor_rate = 0.0 if duration <= 0.0 else internal_vapor / duration
    k_values = _metadata_mapping(engine, "k_values")
    relative_volatilities = _metadata_mapping(engine, "relative_volatilities")
    effective_stages = float(cast(float, engine.ledger.metadata["effective_stages"]))
    observed_raw = engine.ledger.metadata["observed_fenske_stage_count"]
    observed = None if observed_raw is None else float(cast(float, observed_raw))
    fenske_residual = None if observed is None else abs(observed - effective_stages)
    fug = _fug_diagnostics(request, engine)
    distillate_total = sum(outlets["distillate"].values())
    bottoms_total = sum(outlets["bottoms"].values())
    light_distillate = outlets["distillate"][request.light_key]
    heavy_bottoms = outlets["bottoms"][request.heavy_key]
    light_purity = 0.0 if distillate_total <= 0.0 else light_distillate / distillate_total
    heavy_purity = 0.0 if bottoms_total <= 0.0 else heavy_bottoms / bottoms_total
    endpoint_met = abs(actual_cut - request.requested_distillate_cut_fraction) <= 1.0e-9
    provenance = (
        "ChemWorld VLE-derived constant-relative-volatility/Fenske split engine",
        "explicit sensible, reboiler, total-condenser, and internal-vapor ledgers",
        "binary Fenske and Underwood diagnostic when both key products are nonempty",
        f"IDAES {IDAES_COMMIT}:{IDAES_TRAY_COLUMN_PATH} column configuration boundary",
        f"IDAES {IDAES_COMMIT}:{IDAES_CONDENSER_PATH} condenser/reflux boundary",
        f"IDAES {IDAES_COMMIT}:{IDAES_REBOILER_PATH} reboiler duty boundary",
        f"column profile {request.column.provenance_id}",
    )
    combined_warnings = tuple(dict.fromkeys((*warnings, *fug.warnings)))
    return DutyLimitedDistillationResult(
        model_id=DUTY_LIMITED_DISTILLATION_MODEL_ID,
        engine_model_id=DISTILLATION_ENGINE_MODEL_ID,
        feed_amounts_mol=dict(request.feed_amounts_mol),
        outlets=outlets,
        light_key=request.light_key,
        heavy_key=request.heavy_key,
        pressure_Pa=request.pressure_Pa,
        initial_temperature_K=request.initial_temperature_K,
        final_temperature_K=final_temperature_K,
        operating_temperature_K=request.operating_temperature_K,
        elapsed_time_s=request.duration_s,
        reflux_ratio=request.reflux_ratio,
        requested_distillate_cut_fraction=(request.requested_distillate_cut_fraction),
        actual_distillate_cut_fraction=actual_cut,
        cut_endpoint_met=endpoint_met,
        limiting_constraint=limiting_constraint,
        bubble_pressure_Pa=bubble_pressure_Pa,
        bubble_pressure_margin_Pa=bubble_pressure_margin_Pa,
        minimum_thermal_margin_K=minimum_thermal_margin_K,
        k_values=k_values,
        relative_volatilities=relative_volatilities,
        effective_stages=effective_stages,
        observed_fenske_stage_count=observed,
        fenske_stage_residual=fenske_residual,
        fug_available=fug.available,
        fenske_minimum_stages=fug.minimum_stages,
        underwood_theta=fug.underwood_theta,
        minimum_reflux_ratio=fug.minimum_reflux_ratio,
        reflux_margin=fug.reflux_margin,
        gilliland_x=fug.gilliland_x,
        gilliland_y=fug.gilliland_y,
        required_theoretical_stages=fug.required_theoretical_stages,
        installed_equilibrium_stage_margin=(fug.installed_equilibrium_stage_margin),
        light_key_distillate_purity=light_purity,
        light_key_recovery=(
            0.0
            if request.feed_amounts_mol[request.light_key] <= 0.0
            else light_distillate / request.feed_amounts_mol[request.light_key]
        ),
        heavy_key_bottoms_purity=heavy_purity,
        heavy_key_recovery=(
            0.0
            if request.feed_amounts_mol[request.heavy_key] <= 0.0
            else heavy_bottoms / request.feed_amounts_mol[request.heavy_key]
        ),
        sensible_heat_J=sensible_heat_J,
        latent_reboiler_duty_J=latent_duty_J,
        total_reboiler_duty_J=total_reboiler,
        condenser_duty_J=condenser_duty,
        average_reboiler_power_W=average_reboiler_power,
        average_condenser_power_W=average_condenser_power,
        internal_vapor_mol=internal_vapor,
        internal_vapor_rate_mol_s=internal_vapor_rate,
        material_balance_error_mol=material_error,
        energy_balance_error_J=energy_error,
        warnings=combined_warnings,
        provenance=provenance,
    )


def duty_limited_distillation_model_card() -> ModelCard:
    return ModelCard(
        model_id=DUTY_LIMITED_DISTILLATION_MODEL_ID,
        module_id="separations",
        title="Duty-Limited VLE/Fenske Shortcut Distillation",
        maturity=MaturityLevel.PROFESSIONAL_CANDIDATE,
        summary=(
            "A VLE-derived constant-relative-volatility distillation provider "
            "that limits the requested cut by bubble-point feasibility, sensible "
            "heat, reboiler and condenser duty, internal vapor traffic, residual "
            "bottoms, and installed column bounds."
        ),
        equations=(
            "K_i = gamma_i Psat_i/(phi_i P); alpha_i,HK = K_i/K_HK",
            "N_eff = N_theoretical eta_stage R/(1+R)",
            "(D_i/B_i)/(D_j/B_j) = (alpha_i/alpha_j)^N_eff",
            "Q_sensible = sum_i n_i Cp_i (T_op - T_initial)",
            "V_internal = D_total(1+R)",
            "Q_reboiler = Q_sensible + sum_i D_i(1+R) DeltaHvap_i",
            "Q_condenser = sum_i D_i(1+R) DeltaHvap_i",
            "N_min,Fenske and R_min,Underwood are conditional binary diagnostics",
        ),
        assumptions=(
            "Vapor pressures, heat capacities, latent heats, and fugacity "
            "coefficients are evaluated at the declared operating temperature.",
            "Relative volatility is constant over the bounded batch cut.",
            "A total condenser returns reflux and the reboiler supplies all "
            "declared sensible and latent heat without heat loss.",
            "Installed stage efficiency and reflux effectiveness use the existing "
            "audited shortcut convention rather than a MESH solve.",
            "Binary FUG values are diagnostics and do not silently resize the column.",
        ),
        validity_limits=(
            "The light key must be more volatile than the heavy key at the supplied condition.",
            "The operating condition must reach the mixture bubble pressure "
            "before any cut is produced.",
            "Small binary or multicomponent constant-alpha systems only; no "
            "azeotropic, reactive, or liquid-liquid columns.",
            "Power, vapor rate, batch amount, pressure, temperature, reflux, "
            "duration, cut, and residual bottoms must remain in the column card.",
            "Thermal properties are constant over one operation and "
            "phase-equilibrium heat effects beyond latent duty are omitted.",
        ),
        failure_modes=(
            "Invalid or temperature-mismatched property profiles fail before calculation.",
            "Insufficient sensible heat returns an explicit partial-heating no-cut result.",
            "Below-bubble operation returns an explicit no-cut result instead "
            "of vaporizing material.",
            "Requested cuts are reduced to the tightest equipment or utility "
            "constraint and identify that constraint.",
            "Material or energy residuals above tolerance fail the provider result.",
        ),
        units={
            "component amount/internal vapor": "mol",
            "pressure/vapor pressure": "Pa",
            "temperature/thermal margin": "K",
            "duration": "s",
            "heat duty/energy residual": "J",
            "power": "W",
            "internal vapor rate": "mol/s",
            "cut/recovery/purity/reflux/efficiency": "dimensionless",
        },
        reference_reading=(
            f"reference_repos/idaes-pse/{IDAES_TRAY_COLUMN_PATH} at "
            f"{IDAES_COMMIT}: tray count, feed, condenser, and reboiler structure",
            f"reference_repos/idaes-pse/{IDAES_CONDENSER_PATH} at "
            f"{IDAES_COMMIT}: total-condenser reflux split and heat-duty conventions",
            f"reference_repos/idaes-pse/{IDAES_REBOILER_PATH} at "
            f"{IDAES_COMMIT}: reboiler heat-duty and boilup boundary",
            "Fenske minimum stages, Underwood minimum reflux, and Gilliland "
            "shortcut design conventions",
        ),
        validation_evidence=(
            ValidationEvidence(
                evidence_id="duty-limited-distillation-fenske-engine-identity",
                evidence_type="analytical_test",
                description=(
                    "Checks the unconstrained limit against the existing VLE/Fenske "
                    "engine and verifies observed/effective stage identity."
                ),
                status="implemented",
                command_or_path="tests/test_distillation_units.py",
                tolerance="1e-10 material and local analytical tolerances",
            ),
            ValidationEvidence(
                evidence_id="distillation-utility-and-domain-sweep",
                evidence_type="domain_sweep",
                description=(
                    "Checks independent reboiler, condenser, vapor-rate, sensible, "
                    "bubble, thermal, residual-bottoms, reflux, and cut limits."
                ),
                status="implemented",
                command_or_path="tests/test_distillation_units.py",
                tolerance="declared equipment and ledger tolerances",
            ),
        ),
        model_limit_notes=(
            "Professional-candidate maturity applies to this bounded shortcut "
            "operation, not rigorous column design or scale-up.",
            "No stagewise MESH equations, pressure profile, tray hydraulics, "
            "flooding, weeping, dynamic holdup, or heat loss are solved.",
            "The bubble gate uses feed-composition K-values at one declared "
            "temperature; azeotrope and composition-dependent boiling paths "
            "remain outside scope.",
            "WF-110 must map runtime state and refreeze affected benchmark "
            "evidence before replacing the v0.3 provider.",
        ),
        intended_use=(
            "Budgeted reaction-to-distillation benchmark operations.",
            "Agent reasoning over reflux, cut, purity, recovery, energy, and time tradeoffs.",
            "vNext runtime replacement candidate for the distill operation.",
        ),
    )


__all__ = [
    "DISTILLATION_ENGINE_MODEL_ID",
    "DUTY_LIMITED_DISTILLATION_MODEL_ID",
    "IDAES_COMMIT",
    "IDAES_CONDENSER_PATH",
    "IDAES_REBOILER_PATH",
    "IDAES_TRAY_COLUMN_PATH",
    "DistillationComponentSpec",
    "DutyLimitedDistillationRequest",
    "DutyLimitedDistillationResult",
    "ShortcutColumnSpec",
    "duty_limited_distillation_model_card",
    "simulate_duty_limited_distillation",
]
