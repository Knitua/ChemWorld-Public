"""Vapor-pressure property reports and derivatives."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from chemworld.physchem.property_equations import (
    _convert_input,
    _evaluate_temperature_derivative,
    _vapor_pressure_method_family,
    evaluate_correlation,
)
from chemworld.physchem.property_reports import (
    PropertyEvaluation,
    ValidityPolicy,
    _pressure_unit_to_pa_factor,
)
from chemworld.physchem.specs import PropertyCorrelation


@dataclass(frozen=True)
class VaporPressureReport:
    """Vapor/sublimation pressure with derivative and method provenance."""

    pressure: PropertyEvaluation
    temperature_derivative_value: float
    temperature_derivative_unit: str
    dln_pressure_dT_1_K: float
    method_family: str
    validity_status: str
    reference_reading: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.pressure.property_id not in {"vapor_pressure", "sublimation_pressure"}:
            raise ValueError("VaporPressureReport requires vapor or sublimation pressure")
        if not isfinite(self.temperature_derivative_value):
            raise ValueError("temperature derivative must be finite")
        if self.pressure.value <= 0:
            raise ValueError("pressure value must be positive")
        if not isfinite(self.dln_pressure_dT_1_K):
            raise ValueError("log-pressure derivative must be finite")
        if self.validity_status not in {"valid", "out_of_range"}:
            raise ValueError("validity_status must be valid or out_of_range")
        object.__setattr__(self, "reference_reading", tuple(self.reference_reading))

    @property
    def pressure_pa(self) -> float:
        return self.pressure.to("Pa").value

    @property
    def dp_dt_pa_per_k(self) -> float:
        return self.temperature_derivative_value * _pressure_unit_to_pa_factor(
            self.pressure.unit
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "pressure": self.pressure.to_dict(),
            "temperature_derivative_value": self.temperature_derivative_value,
            "temperature_derivative_unit": self.temperature_derivative_unit,
            "dP_dT_Pa_per_K": self.dp_dt_pa_per_k,
            "dln_pressure_dT_1_K": self.dln_pressure_dT_1_K,
            "method_family": self.method_family,
            "validity_status": self.validity_status,
            "reference_reading": list(self.reference_reading),
        }


def vapor_pressure_report(
    correlation: PropertyCorrelation,
    *,
    temperature_K: float,
    validity_policy: ValidityPolicy = "warn",
) -> VaporPressureReport:
    """Evaluate pressure and analytic temperature derivative for vapor models."""

    if correlation.property_id not in {"vapor_pressure", "sublimation_pressure"}:
        raise ValueError("vapor_pressure_report requires vapor or sublimation pressure")
    pressure = evaluate_correlation(
        correlation,
        temperature_K=temperature_K,
        validity_policy=validity_policy,
    )
    derivative = vapor_pressure_temperature_derivative(
        correlation,
        temperature_K=temperature_K,
        validity_policy=validity_policy,
    )
    pressure_value = pressure.value
    dln = derivative.value / pressure_value
    return VaporPressureReport(
        pressure=pressure,
        temperature_derivative_value=derivative.value,
        temperature_derivative_unit=derivative.unit,
        dln_pressure_dT_1_K=dln,
        method_family=_vapor_pressure_method_family(correlation.equation_id),
        validity_status="valid" if not pressure.warnings else "out_of_range",
        reference_reading=(
            "reference_repos/chemicals/chemicals/vapor_pressure.py: "
            "Antoine, Wagner, dWagner_dT",
            "reference_repos/chemicals/chemicals/dippr.py: EQ101 order=1 "
            "derivative",
            "reference_repos/thermo/thermo/vapor_pressure.py: "
            "VaporPressure ranked methods and validity limits",
        ),
    )


def vapor_pressure_temperature_derivative(
    correlation: PropertyCorrelation,
    *,
    temperature_K: float,
    validity_policy: ValidityPolicy = "warn",
) -> PropertyEvaluation:
    """Analytic `dP_sat/dT` in the correlation output unit per kelvin."""

    if correlation.property_id not in {"vapor_pressure", "sublimation_pressure"}:
        raise ValueError(
            "vapor_pressure_temperature_derivative requires vapor or "
            "sublimation pressure"
        )
    pressure = evaluate_correlation(
        correlation,
        temperature_K=temperature_K,
        validity_policy=validity_policy,
    )
    inputs = {
        "temperature": _convert_input(temperature_K, "K", correlation, "temperature")
    }
    derivative = _evaluate_temperature_derivative(
        correlation,
        inputs=inputs,
        pressure_value=pressure.value,
    )
    if not isfinite(derivative):
        raise ValueError(
            f"Correlation derivative returned non-finite value: "
            f"{correlation.correlation_id}"
        )
    return PropertyEvaluation(
        property_id=f"{correlation.property_id}_temperature_derivative",
        correlation_id=f"{correlation.correlation_id}:dP_dT",
        equation_id=f"{correlation.equation_id}_temperature_derivative",
        value=derivative,
        unit=f"{correlation.output_unit}/K",
        inputs=inputs,
        warnings=pressure.warnings,
    )

