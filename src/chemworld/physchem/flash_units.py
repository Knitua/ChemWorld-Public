"""Auditable TP flash unit with material, phase, and enthalpy ledgers."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from math import isfinite

from chemworld.physchem.equilibrium import (
    ActivityModelSpec,
    gamma_phi_k_value_report,
    rachford_rice_diagnostic_report,
)


@dataclass(frozen=True)
class TPFlashUnitResult:
    model_id: str
    temperature_K: float
    pressure_Pa: float
    feed_amounts_mol: dict[str, float]
    vapor_fraction: float
    liquid_amounts_mol: dict[str, float]
    vapor_amounts_mol: dict[str, float]
    liquid_composition: dict[str, float]
    vapor_composition: dict[str, float]
    k_values: dict[str, float]
    activity_coefficients: dict[str, float]
    vapor_fugacity_coefficients: dict[str, float]
    feed_enthalpy_J: float
    liquid_enthalpy_J: float
    vapor_enthalpy_J: float
    heat_duty_J: float
    material_balance_error_mol: float
    energy_balance_error_J: float
    iterations: int
    converged: bool
    phase_status: str
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "model_id": self.model_id,
            "temperature_K": self.temperature_K,
            "pressure_Pa": self.pressure_Pa,
            "feed_amounts_mol": dict(self.feed_amounts_mol),
            "vapor_fraction": self.vapor_fraction,
            "liquid_amounts_mol": dict(self.liquid_amounts_mol),
            "vapor_amounts_mol": dict(self.vapor_amounts_mol),
            "liquid_composition": dict(self.liquid_composition),
            "vapor_composition": dict(self.vapor_composition),
            "k_values": dict(self.k_values),
            "activity_coefficients": dict(self.activity_coefficients),
            "vapor_fugacity_coefficients": dict(self.vapor_fugacity_coefficients),
            "feed_enthalpy_J": self.feed_enthalpy_J,
            "liquid_enthalpy_J": self.liquid_enthalpy_J,
            "vapor_enthalpy_J": self.vapor_enthalpy_J,
            "heat_duty_J": self.heat_duty_J,
            "material_balance_error_mol": self.material_balance_error_mol,
            "energy_balance_error_J": self.energy_balance_error_J,
            "iterations": self.iterations,
            "converged": self.converged,
            "phase_status": self.phase_status,
            "warnings": list(self.warnings),
        }


def tp_flash_with_energy_balance(
    feed_amounts_mol: Mapping[str, float],
    *,
    temperature_K: float,
    pressure_Pa: float,
    vapor_pressures_Pa: Mapping[str, float],
    feed_molar_enthalpies_J_mol: Mapping[str, float],
    liquid_molar_enthalpies_J_mol: Mapping[str, float],
    vapor_molar_enthalpies_J_mol: Mapping[str, float],
    activity_model: ActivityModelSpec | None = None,
    vapor_fugacity_coefficients: Mapping[str, float] | None = None,
    liquid_reference_fugacity_coefficients: Mapping[str, float] | None = None,
    poynting_factors: Mapping[str, float] | None = None,
    tolerance: float = 1.0e-10,
    max_iterations: int = 100,
) -> TPFlashUnitResult:
    """Solve a fixed-TP gamma-phi flash and close material/enthalpy ledgers."""

    if temperature_K <= 0.0 or not isfinite(temperature_K):
        raise ValueError("temperature_K must be finite and positive")
    if pressure_Pa <= 0.0 or not isfinite(pressure_Pa):
        raise ValueError("pressure_Pa must be finite and positive")
    if tolerance <= 0.0 or not isfinite(tolerance):
        raise ValueError("tolerance must be finite and positive")
    if max_iterations <= 0:
        raise ValueError("max_iterations must be positive")
    feed = _positive_amounts(feed_amounts_mol)
    component_ids = tuple(feed)
    total_feed = sum(feed.values())
    overall = {component_id: amount / total_feed for component_id, amount in feed.items()}
    _require_component_mapping(component_ids, vapor_pressures_Pa, "vapor_pressures_Pa")
    _require_component_mapping(
        component_ids,
        feed_molar_enthalpies_J_mol,
        "feed_molar_enthalpies_J_mol",
        positive=False,
    )
    _require_component_mapping(
        component_ids,
        liquid_molar_enthalpies_J_mol,
        "liquid_molar_enthalpies_J_mol",
        positive=False,
    )
    _require_component_mapping(
        component_ids,
        vapor_molar_enthalpies_J_mol,
        "vapor_molar_enthalpies_J_mol",
        positive=False,
    )
    resolved_activity = activity_model or ActivityModelSpec(
        "ideal_tp_flash",
        component_ids,
        "ideal",
    )
    if set(resolved_activity.component_ids) != set(component_ids):
        raise ValueError("activity_model components must match feed components")

    liquid_guess = dict(overall)
    converged = False
    report = None
    phase = None
    iterations = 0
    for iteration in range(1, max_iterations + 1):
        iterations = iteration
        report = gamma_phi_k_value_report(
            resolved_activity,
            liquid_guess,
            vapor_pressures_Pa=vapor_pressures_Pa,
            pressure_Pa=pressure_Pa,
            temperature_K=temperature_K,
            vapor_fugacity_coefficients=vapor_fugacity_coefficients,
            liquid_reference_fugacity_coefficients=liquid_reference_fugacity_coefficients,
            poynting_factors=poynting_factors,
        )
        phase = rachford_rice_diagnostic_report(overall, report.k_values)
        error = max(abs(phase.liquid_composition[key] - liquid_guess[key]) for key in component_ids)
        if error <= tolerance:
            converged = True
            break
        liquid_guess = {
            key: 0.5 * liquid_guess[key] + 0.5 * phase.liquid_composition[key]
            for key in component_ids
        }
    if report is None or phase is None:  # pragma: no cover - loop is guaranteed above
        raise RuntimeError("TP flash did not execute")

    liquid_total = total_feed * (1.0 - phase.vapor_fraction)
    vapor_total = total_feed * phase.vapor_fraction
    liquid_amounts = {key: liquid_total * phase.liquid_composition[key] for key in component_ids}
    vapor_amounts = {key: vapor_total * phase.vapor_composition[key] for key in component_ids}
    material_error = sum(
        abs(feed[key] - liquid_amounts[key] - vapor_amounts[key]) for key in component_ids
    )
    feed_enthalpy = sum(
        feed[key] * float(feed_molar_enthalpies_J_mol[key]) for key in component_ids
    )
    liquid_enthalpy = sum(
        liquid_amounts[key] * float(liquid_molar_enthalpies_J_mol[key]) for key in component_ids
    )
    vapor_enthalpy = sum(
        vapor_amounts[key] * float(vapor_molar_enthalpies_J_mol[key]) for key in component_ids
    )
    heat_duty = liquid_enthalpy + vapor_enthalpy - feed_enthalpy
    energy_error = abs(feed_enthalpy + heat_duty - liquid_enthalpy - vapor_enthalpy)
    warnings = list(phase.warnings)
    if not converged:
        warnings.append("gamma_phi_iteration_not_converged")
    return TPFlashUnitResult(
        model_id="tp_gamma_phi_flash_energy_balance_v1",
        temperature_K=temperature_K,
        pressure_Pa=pressure_Pa,
        feed_amounts_mol=feed,
        vapor_fraction=phase.vapor_fraction,
        liquid_amounts_mol=liquid_amounts,
        vapor_amounts_mol=vapor_amounts,
        liquid_composition=phase.liquid_composition,
        vapor_composition=phase.vapor_composition,
        k_values=report.k_values,
        activity_coefficients=report.activity_coefficients,
        vapor_fugacity_coefficients=report.vapor_fugacity_coefficients,
        feed_enthalpy_J=feed_enthalpy,
        liquid_enthalpy_J=liquid_enthalpy,
        vapor_enthalpy_J=vapor_enthalpy,
        heat_duty_J=heat_duty,
        material_balance_error_mol=material_error,
        energy_balance_error_J=energy_error,
        iterations=iterations,
        converged=converged,
        phase_status=phase.phase_status,
        warnings=tuple(warnings),
    )


def _positive_amounts(values: Mapping[str, float]) -> dict[str, float]:
    if not values:
        raise ValueError("feed_amounts_mol cannot be empty")
    result = {str(key): float(value) for key, value in values.items()}
    if any(value < 0.0 or not isfinite(value) for value in result.values()):
        raise ValueError("feed_amounts_mol must contain finite nonnegative values")
    if sum(result.values()) <= 0.0:
        raise ValueError("feed_amounts_mol must contain positive total material")
    return result


def _require_component_mapping(
    component_ids: tuple[str, ...],
    values: Mapping[str, float],
    field_name: str,
    *,
    positive: bool = True,
) -> None:
    if set(values) != set(component_ids):
        raise ValueError(f"{field_name} keys must exactly match feed components")
    converted = [float(values[key]) for key in component_ids]
    if any(not isfinite(value) for value in converted):
        raise ValueError(f"{field_name} must contain finite values")
    if positive and any(value <= 0.0 for value in converted):
        raise ValueError(f"{field_name} must contain positive values")


__all__ = ["TPFlashUnitResult", "tp_flash_with_energy_balance"]
