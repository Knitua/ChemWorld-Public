"""Pressure-temperature safety envelopes and runaway indicators."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

R_J_PER_MOL_K = 8.31446261815324


@dataclass(frozen=True)
class SafetyEnvelopeSpec:
    envelope_id: str
    temperature_warning_K: float
    maximum_allowable_temperature_K: float
    pressure_warning_Pa: float
    relief_set_pressure_Pa: float
    maximum_allowable_pressure_Pa: float
    relief_capacity_kg_s: float
    risk_cost_weight: float
    relief_activation_cost: float
    emergency_shutdown_cost: float
    provenance_id: str

    def __post_init__(self) -> None:
        for name, value in (
            ("temperature_warning_K", self.temperature_warning_K),
            (
                "maximum_allowable_temperature_K",
                self.maximum_allowable_temperature_K,
            ),
            ("pressure_warning_Pa", self.pressure_warning_Pa),
            ("relief_set_pressure_Pa", self.relief_set_pressure_Pa),
            ("maximum_allowable_pressure_Pa", self.maximum_allowable_pressure_Pa),
            ("relief_capacity_kg_s", self.relief_capacity_kg_s),
        ):
            _positive(value, name)
        for name, value in (
            ("risk_cost_weight", self.risk_cost_weight),
            ("relief_activation_cost", self.relief_activation_cost),
            ("emergency_shutdown_cost", self.emergency_shutdown_cost),
        ):
            _nonnegative(value, name)
        if self.temperature_warning_K >= self.maximum_allowable_temperature_K:
            raise ValueError("temperature warning must be below maximum")
        if not (
            self.pressure_warning_Pa
            < self.relief_set_pressure_Pa
            <= self.maximum_allowable_pressure_Pa
        ):
            raise ValueError("pressure limits must satisfy warning < relief set <= maximum")
        if not self.envelope_id or not self.provenance_id:
            raise ValueError("envelope_id and provenance_id cannot be empty")

    def to_dict(self) -> dict[str, object]:
        return {
            "envelope_id": self.envelope_id,
            "temperature_warning_K": self.temperature_warning_K,
            "maximum_allowable_temperature_K": (self.maximum_allowable_temperature_K),
            "pressure_warning_Pa": self.pressure_warning_Pa,
            "relief_set_pressure_Pa": self.relief_set_pressure_Pa,
            "maximum_allowable_pressure_Pa": self.maximum_allowable_pressure_Pa,
            "relief_capacity_kg_s": self.relief_capacity_kg_s,
            "risk_cost_weight": self.risk_cost_weight,
            "relief_activation_cost": self.relief_activation_cost,
            "emergency_shutdown_cost": self.emergency_shutdown_cost,
            "provenance_id": self.provenance_id,
        }


@dataclass(frozen=True)
class RunawayStateInput:
    heat_generation_W: float
    heat_removal_W: float
    heat_removal_slope_W_K: float
    activation_energy_J_mol: float
    process_heat_capacity_J_K: float
    remaining_exotherm_J: float
    pressure_rate_Pa_s: float
    vapor_generation_kg_s: float

    def __post_init__(self) -> None:
        for name, value in (
            ("heat_generation_W", self.heat_generation_W),
            ("heat_removal_W", self.heat_removal_W),
            ("heat_removal_slope_W_K", self.heat_removal_slope_W_K),
            ("activation_energy_J_mol", self.activation_energy_J_mol),
            ("remaining_exotherm_J", self.remaining_exotherm_J),
            ("vapor_generation_kg_s", self.vapor_generation_kg_s),
        ):
            _nonnegative(value, name)
        _positive(self.process_heat_capacity_J_K, "process_heat_capacity_J_K")
        if not isfinite(self.pressure_rate_Pa_s):
            raise ValueError("pressure_rate_Pa_s must be finite")

    def to_dict(self) -> dict[str, float]:
        return {
            "heat_generation_W": self.heat_generation_W,
            "heat_removal_W": self.heat_removal_W,
            "heat_removal_slope_W_K": self.heat_removal_slope_W_K,
            "activation_energy_J_mol": self.activation_energy_J_mol,
            "process_heat_capacity_J_K": self.process_heat_capacity_J_K,
            "remaining_exotherm_J": self.remaining_exotherm_J,
            "pressure_rate_Pa_s": self.pressure_rate_Pa_s,
            "vapor_generation_kg_s": self.vapor_generation_kg_s,
        }


@dataclass(frozen=True)
class SafetyEnvelopeAssessment:
    model_id: str
    envelope_id: str
    status: str
    temperature_K: float
    pressure_Pa: float
    net_heat_accumulation_W: float
    predicted_temperature_rate_K_s: float
    arrhenius_heat_generation_slope_W_K: float
    heat_removal_slope_W_K: float
    runaway_slope_ratio: float
    runaway_stability_margin_W_K: float
    adiabatic_temperature_rise_K: float
    maximum_temperature_of_synthesis_reaction_K: float
    relief_load_ratio: float
    time_to_temperature_limit_s: float | None
    time_to_relief_set_s: float | None
    temperature_severity: float
    pressure_severity: float
    thermal_runaway_severity: float
    relief_severity: float
    risk_score: float
    incremental_safety_cost: float
    flags: tuple[str, ...]
    provenance_id: str

    def constraint_flags(self) -> dict[str, bool | float]:
        """Return fields suitable for Gym constraint and cost adapters."""

        return {
            "unsafe": self.status in {"relief_required", "emergency_shutdown"},
            "relief_required": self.status == "relief_required",
            "emergency_shutdown": self.status == "emergency_shutdown",
            "safety_risk": self.risk_score,
            "incremental_safety_cost": self.incremental_safety_cost,
        }

    def to_dict(self) -> dict[str, object]:
        return {
            "model_id": self.model_id,
            "envelope_id": self.envelope_id,
            "status": self.status,
            "temperature_K": self.temperature_K,
            "pressure_Pa": self.pressure_Pa,
            "net_heat_accumulation_W": self.net_heat_accumulation_W,
            "predicted_temperature_rate_K_s": self.predicted_temperature_rate_K_s,
            "arrhenius_heat_generation_slope_W_K": (self.arrhenius_heat_generation_slope_W_K),
            "heat_removal_slope_W_K": self.heat_removal_slope_W_K,
            "runaway_slope_ratio": self.runaway_slope_ratio,
            "runaway_stability_margin_W_K": self.runaway_stability_margin_W_K,
            "adiabatic_temperature_rise_K": self.adiabatic_temperature_rise_K,
            "maximum_temperature_of_synthesis_reaction_K": (
                self.maximum_temperature_of_synthesis_reaction_K
            ),
            "relief_load_ratio": self.relief_load_ratio,
            "time_to_temperature_limit_s": self.time_to_temperature_limit_s,
            "time_to_relief_set_s": self.time_to_relief_set_s,
            "temperature_severity": self.temperature_severity,
            "pressure_severity": self.pressure_severity,
            "thermal_runaway_severity": self.thermal_runaway_severity,
            "relief_severity": self.relief_severity,
            "risk_score": self.risk_score,
            "incremental_safety_cost": self.incremental_safety_cost,
            "flags": list(self.flags),
            "provenance_id": self.provenance_id,
            "constraint_flags": self.constraint_flags(),
        }


def assess_safety_envelope(
    envelope: SafetyEnvelopeSpec,
    *,
    temperature_K: float,
    pressure_Pa: float,
    runaway: RunawayStateInput,
) -> SafetyEnvelopeAssessment:
    """Assess current and projected thermal/pressure safety indicators."""

    _positive(temperature_K, "temperature_K")
    _positive(pressure_Pa, "pressure_Pa")
    net_heat = runaway.heat_generation_W - runaway.heat_removal_W
    temperature_rate = net_heat / runaway.process_heat_capacity_J_K
    generation_slope = arrhenius_heat_generation_slope(
        heat_generation_W=runaway.heat_generation_W,
        activation_energy_J_mol=runaway.activation_energy_J_mol,
        temperature_K=temperature_K,
    )
    removal_slope = runaway.heat_removal_slope_W_K
    runaway_slope_ratio = (
        generation_slope / removal_slope
        if removal_slope > 0.0
        else (1.0 if generation_slope == 0.0 else 1.0e12)
    )
    stability_margin = removal_slope - generation_slope
    adiabatic_rise = runaway.remaining_exotherm_J / runaway.process_heat_capacity_J_K
    mtsr = temperature_K + adiabatic_rise
    relief_load_ratio = runaway.vapor_generation_kg_s / envelope.relief_capacity_kg_s
    time_to_temperature = _time_to_upper_limit(
        value=temperature_K,
        rate=temperature_rate,
        limit=envelope.maximum_allowable_temperature_K,
    )
    time_to_relief = _time_to_upper_limit(
        value=pressure_Pa,
        rate=runaway.pressure_rate_Pa_s,
        limit=envelope.relief_set_pressure_Pa,
    )
    temperature_severity = _severity(
        temperature_K,
        envelope.temperature_warning_K,
        envelope.maximum_allowable_temperature_K,
    )
    pressure_severity = _severity(
        pressure_Pa,
        envelope.pressure_warning_Pa,
        envelope.maximum_allowable_pressure_Pa,
    )
    mtsr_severity = _severity(
        mtsr,
        envelope.temperature_warning_K,
        envelope.maximum_allowable_temperature_K,
    )
    slope_severity = _clip01((runaway_slope_ratio - 0.8) / 1.2)
    accumulation_fraction = max(net_heat, 0.0) / max(
        runaway.heat_generation_W,
        1.0e-12,
    )
    thermal_runaway_severity = _clip01(
        0.45 * mtsr_severity + 0.35 * slope_severity + 0.20 * accumulation_fraction
    )
    relief_severity = max(
        _clip01((relief_load_ratio - 0.8) / 0.2),
        _severity(
            pressure_Pa,
            envelope.pressure_warning_Pa,
            envelope.relief_set_pressure_Pa,
        ),
    )
    risk_score = _clip01(
        0.28 * temperature_severity
        + 0.27 * pressure_severity
        + 0.30 * thermal_runaway_severity
        + 0.15 * relief_severity
    )

    flags: list[str] = []
    if temperature_K >= envelope.temperature_warning_K:
        flags.append("temperature_warning")
    if temperature_K >= envelope.maximum_allowable_temperature_K:
        flags.append("maximum_temperature_exceeded")
    if pressure_Pa >= envelope.pressure_warning_Pa:
        flags.append("pressure_warning")
    if pressure_Pa >= envelope.relief_set_pressure_Pa:
        flags.append("relief_set_pressure_reached")
    if pressure_Pa >= envelope.maximum_allowable_pressure_Pa:
        flags.append("maximum_allowable_pressure_exceeded")
    if relief_load_ratio > 1.0:
        flags.append("relief_capacity_insufficient")
    if mtsr >= envelope.maximum_allowable_temperature_K:
        flags.append("mtsr_exceeds_maximum_temperature")
    if generation_slope > removal_slope:
        flags.append("thermal_runaway_slope_unstable")
    if net_heat > 0.0:
        flags.append("net_heat_accumulation")

    emergency = any(
        flag
        in {
            "maximum_temperature_exceeded",
            "maximum_allowable_pressure_exceeded",
            "relief_capacity_insufficient",
        }
        for flag in flags
    )
    relief_required = "relief_set_pressure_reached" in flags
    warning = bool(flags)
    status = (
        "emergency_shutdown"
        if emergency
        else "relief_required"
        if relief_required
        else "warning"
        if warning
        else "normal"
    )
    incremental_cost = envelope.risk_cost_weight * risk_score
    if relief_required:
        incremental_cost += envelope.relief_activation_cost
    if emergency:
        incremental_cost += envelope.emergency_shutdown_cost
    return SafetyEnvelopeAssessment(
        model_id="pressure_temperature_runaway_safety_envelope_v1",
        envelope_id=envelope.envelope_id,
        status=status,
        temperature_K=temperature_K,
        pressure_Pa=pressure_Pa,
        net_heat_accumulation_W=net_heat,
        predicted_temperature_rate_K_s=temperature_rate,
        arrhenius_heat_generation_slope_W_K=generation_slope,
        heat_removal_slope_W_K=removal_slope,
        runaway_slope_ratio=runaway_slope_ratio,
        runaway_stability_margin_W_K=stability_margin,
        adiabatic_temperature_rise_K=adiabatic_rise,
        maximum_temperature_of_synthesis_reaction_K=mtsr,
        relief_load_ratio=relief_load_ratio,
        time_to_temperature_limit_s=time_to_temperature,
        time_to_relief_set_s=time_to_relief,
        temperature_severity=temperature_severity,
        pressure_severity=pressure_severity,
        thermal_runaway_severity=thermal_runaway_severity,
        relief_severity=relief_severity,
        risk_score=risk_score,
        incremental_safety_cost=incremental_cost,
        flags=tuple(flags),
        provenance_id=envelope.provenance_id,
    )


def arrhenius_heat_generation_slope(
    *,
    heat_generation_W: float,
    activation_energy_J_mol: float,
    temperature_K: float,
) -> float:
    """Return dQ/dT for a local Arrhenius heat-generation approximation."""

    _nonnegative(heat_generation_W, "heat_generation_W")
    _nonnegative(activation_energy_J_mol, "activation_energy_J_mol")
    _positive(temperature_K, "temperature_K")
    return heat_generation_W * activation_energy_J_mol / (R_J_PER_MOL_K * temperature_K**2)


def _time_to_upper_limit(*, value: float, rate: float, limit: float) -> float | None:
    if value >= limit:
        return 0.0
    if rate <= 0.0:
        return None
    return (limit - value) / rate


def _severity(value: float, warning: float, maximum: float) -> float:
    if value <= warning:
        return 0.0
    return _clip01((value - warning) / (maximum - warning))


def _clip01(value: float) -> float:
    return min(max(float(value), 0.0), 1.0)


def _positive(value: float, field_name: str) -> None:
    if value <= 0.0 or not isfinite(value):
        raise ValueError(f"{field_name} must be positive and finite")


def _nonnegative(value: float, field_name: str) -> None:
    if value < 0.0 or not isfinite(value):
        raise ValueError(f"{field_name} must be nonnegative and finite")


__all__ = [
    "RunawayStateInput",
    "SafetyEnvelopeAssessment",
    "SafetyEnvelopeSpec",
    "arrhenius_heat_generation_slope",
    "assess_safety_envelope",
]
