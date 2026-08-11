"""Property-derived screening hazard proxies."""

from __future__ import annotations

from chemworld.physchem.property_reports import (
    STANDARD_PRESSURE_PA,
    PropertyEvaluation,
    _clamp,
)


def volatility_risk_from_psat(
    vapor_pressure: PropertyEvaluation,
    *,
    ambient_pressure_Pa: float = STANDARD_PRESSURE_PA,
    low_ratio: float = 0.05,
    high_ratio: float = 1.0,
) -> PropertyEvaluation:
    psat_Pa = vapor_pressure.to("Pa").value
    if ambient_pressure_Pa <= 0:
        raise ValueError("ambient_pressure_Pa must be positive")
    ratio = psat_Pa / ambient_pressure_Pa
    risk = _clamp((ratio - low_ratio) / (high_ratio - low_ratio), 0.0, 1.0)
    return PropertyEvaluation(
        property_id="volatility_risk",
        correlation_id=f"{vapor_pressure.correlation_id}:volatility_risk",
        equation_id="volatility_risk_proxy",
        value=risk,
        unit="dimensionless",
        inputs={"vapor_pressure_Pa": psat_Pa, "ambient_pressure_Pa": ambient_pressure_Pa},
    )


def thermal_hazard_proxy(
    *,
    temperature_K: float,
    onset_temperature_K: float,
    severe_temperature_K: float,
) -> PropertyEvaluation:
    if onset_temperature_K >= severe_temperature_K:
        raise ValueError("onset_temperature_K must be below severe_temperature_K")
    risk = _clamp(
        (temperature_K - onset_temperature_K)
        / (severe_temperature_K - onset_temperature_K),
        0.0,
        1.0,
    )
    return PropertyEvaluation(
        property_id="thermal_hazard",
        correlation_id="thermal_hazard_proxy",
        equation_id="linear_thermal_hazard_proxy",
        value=risk,
        unit="dimensionless",
        inputs={
            "temperature_K": temperature_K,
            "onset_temperature_K": onset_temperature_K,
            "severe_temperature_K": severe_temperature_K,
        },
    )

