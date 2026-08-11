"""Separated-flow two-phase pressure-drop correlations."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite, pi, sqrt


@dataclass(frozen=True)
class LockhartMartinelliPressureDropResult:
    model_id: str
    pressure_drop_Pa: float
    liquid_only_pressure_drop_Pa: float
    vapor_only_pressure_drop_Pa: float
    liquid_reynolds: float
    vapor_reynolds: float
    liquid_friction_factor: float
    vapor_friction_factor: float
    martinelli_parameter: float
    liquid_multiplier_squared: float
    chisholm_parameter: float
    liquid_regime: str
    vapor_regime: str
    mass_flow_kg_s: float
    vapor_quality: float
    length_m: float
    diameter_m: float
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "model_id": self.model_id,
            "pressure_drop_Pa": self.pressure_drop_Pa,
            "liquid_only_pressure_drop_Pa": self.liquid_only_pressure_drop_Pa,
            "vapor_only_pressure_drop_Pa": self.vapor_only_pressure_drop_Pa,
            "liquid_reynolds": self.liquid_reynolds,
            "vapor_reynolds": self.vapor_reynolds,
            "liquid_friction_factor": self.liquid_friction_factor,
            "vapor_friction_factor": self.vapor_friction_factor,
            "martinelli_parameter": self.martinelli_parameter,
            "liquid_multiplier_squared": self.liquid_multiplier_squared,
            "chisholm_parameter": self.chisholm_parameter,
            "liquid_regime": self.liquid_regime,
            "vapor_regime": self.vapor_regime,
            "mass_flow_kg_s": self.mass_flow_kg_s,
            "vapor_quality": self.vapor_quality,
            "length_m": self.length_m,
            "diameter_m": self.diameter_m,
            "warnings": list(self.warnings),
        }


def lockhart_martinelli_pressure_drop(
    *,
    mass_flow_kg_s: float,
    vapor_quality: float,
    liquid_density_kg_m3: float,
    vapor_density_kg_m3: float,
    liquid_viscosity_Pa_s: float,
    vapor_viscosity_Pa_s: float,
    diameter_m: float,
    length_m: float = 1.0,
    transition_reynolds: float = 2000.0,
    inclination_degrees: float = 0.0,
) -> LockhartMartinelliPressureDropResult:
    """Return horizontal frictional drop from Lockhart-Martinelli/Chisholm."""

    for name, value in (
        ("mass_flow_kg_s", mass_flow_kg_s),
        ("liquid_density_kg_m3", liquid_density_kg_m3),
        ("vapor_density_kg_m3", vapor_density_kg_m3),
        ("liquid_viscosity_Pa_s", liquid_viscosity_Pa_s),
        ("vapor_viscosity_Pa_s", vapor_viscosity_Pa_s),
        ("diameter_m", diameter_m),
        ("length_m", length_m),
        ("transition_reynolds", transition_reynolds),
    ):
        _positive(value, name)
    if not 0.0 < vapor_quality < 1.0 or not isfinite(vapor_quality):
        raise ValueError("vapor_quality must be finite and inside (0, 1)")
    if abs(inclination_degrees) > 1.0e-12 or not isfinite(inclination_degrees):
        raise ValueError("Lockhart-Martinelli slice is restricted to horizontal flow")

    area_m2 = 0.25 * pi * diameter_m**2
    liquid_velocity = mass_flow_kg_s * (1.0 - vapor_quality) / (liquid_density_kg_m3 * area_m2)
    vapor_velocity = mass_flow_kg_s * vapor_quality / (vapor_density_kg_m3 * area_m2)
    liquid_reynolds = liquid_density_kg_m3 * liquid_velocity * diameter_m / liquid_viscosity_Pa_s
    vapor_reynolds = vapor_density_kg_m3 * vapor_velocity * diameter_m / vapor_viscosity_Pa_s
    liquid_laminar = liquid_reynolds < transition_reynolds
    vapor_laminar = vapor_reynolds < transition_reynolds
    if liquid_laminar and vapor_laminar:
        chisholm = 5.0
    elif liquid_laminar:
        chisholm = 12.0
    elif vapor_laminar:
        chisholm = 10.0
    else:
        chisholm = 20.0
    liquid_friction = _original_darcy_friction_factor(
        liquid_reynolds,
        transition_reynolds,
    )
    vapor_friction = _original_darcy_friction_factor(
        vapor_reynolds,
        transition_reynolds,
    )
    liquid_drop = (
        liquid_friction * length_m / diameter_m * 0.5 * liquid_density_kg_m3 * liquid_velocity**2
    )
    vapor_drop = (
        vapor_friction * length_m / diameter_m * 0.5 * vapor_density_kg_m3 * vapor_velocity**2
    )
    martinelli = sqrt(liquid_drop / vapor_drop)
    liquid_multiplier_squared = 1.0 + chisholm / martinelli + 1.0 / martinelli**2
    pressure_drop = liquid_drop * liquid_multiplier_squared
    warnings: list[str] = []
    if vapor_quality < 0.05 or vapor_quality > 0.95:
        warnings.append("quality_near_single_phase_endpoint")
    if diameter_m < 3.0e-3:
        warnings.append("microchannel_surface_tension_effects_not_modeled")
    if liquid_density_kg_m3 / vapor_density_kg_m3 < 10.0:
        warnings.append("low_density_ratio_outside_common_gas_liquid_use")
    return LockhartMartinelliPressureDropResult(
        model_id="lockhart_martinelli_chisholm_horizontal_v1",
        pressure_drop_Pa=pressure_drop,
        liquid_only_pressure_drop_Pa=liquid_drop,
        vapor_only_pressure_drop_Pa=vapor_drop,
        liquid_reynolds=liquid_reynolds,
        vapor_reynolds=vapor_reynolds,
        liquid_friction_factor=liquid_friction,
        vapor_friction_factor=vapor_friction,
        martinelli_parameter=martinelli,
        liquid_multiplier_squared=liquid_multiplier_squared,
        chisholm_parameter=chisholm,
        liquid_regime="laminar" if liquid_laminar else "turbulent",
        vapor_regime="laminar" if vapor_laminar else "turbulent",
        mass_flow_kg_s=mass_flow_kg_s,
        vapor_quality=vapor_quality,
        length_m=length_m,
        diameter_m=diameter_m,
        warnings=tuple(warnings),
    )


def _original_darcy_friction_factor(
    reynolds: float,
    transition_reynolds: float,
) -> float:
    return 64.0 / reynolds if reynolds < transition_reynolds else 0.184 * reynolds ** (-0.2)


def _positive(value: float, field_name: str) -> None:
    if value <= 0.0 or not isfinite(value):
        raise ValueError(f"{field_name} must be positive and finite")


__all__ = [
    "LockhartMartinelliPressureDropResult",
    "lockhart_martinelli_pressure_drop",
]
