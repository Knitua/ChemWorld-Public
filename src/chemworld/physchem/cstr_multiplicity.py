"""Exothermic CSTR multiplicity reference problem and solver."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from math import exp

import numpy as np
from scipy.optimize import brentq

from chemworld.physchem.reaction_network import (
    RateLawSpec,
    ReactionNetworkSpec,
    ReactionSpec,
    SpeciesSpec,
)
from chemworld.physchem.reactor_shared import SteadyStateStability, _positive


@dataclass(frozen=True)
class CSTRMultiplicitySpec:
    """Scalar exothermic CSTR reference problem for steady-state multiplicity."""

    case_id: str
    feed_concentration_A_mol_L: float
    volumetric_flow_L_s: float
    volume_L: float
    feed_temperature_K: float
    coolant_temperature_K: float
    ua_W_per_K: float
    rho_cp_J_per_L_K: float
    delta_h_J_per_mol: float
    arrhenius_A_s_inv: float
    arrhenius_Ea_J_per_mol: float
    temperature_bounds_K: tuple[float, float]
    species_ids: tuple[str, str] = ("A", "P")

    def __post_init__(self) -> None:
        if not self.case_id.strip():
            raise ValueError("case_id cannot be empty")
        _positive(self.feed_concentration_A_mol_L, "feed_concentration_A_mol_L")
        _positive(self.volumetric_flow_L_s, "volumetric_flow_L_s")
        _positive(self.volume_L, "volume_L")
        _positive(self.feed_temperature_K, "feed_temperature_K")
        _positive(self.coolant_temperature_K, "coolant_temperature_K")
        if self.ua_W_per_K < 0:
            raise ValueError("ua_W_per_K cannot be negative")
        _positive(self.rho_cp_J_per_L_K, "rho_cp_J_per_L_K")
        if self.delta_h_J_per_mol >= 0:
            raise ValueError("CSTR multiplicity case requires an exothermic delta_h_J_per_mol")
        _positive(self.arrhenius_A_s_inv, "arrhenius_A_s_inv")
        _positive(self.arrhenius_Ea_J_per_mol, "arrhenius_Ea_J_per_mol")
        if len(self.species_ids) != 2 or len(set(self.species_ids)) != 2:
            raise ValueError("species_ids must contain two distinct labels")
        low, high = self.temperature_bounds_K
        _positive(low, "temperature_bounds_K[0]")
        _positive(high, "temperature_bounds_K[1]")
        if high <= low:
            raise ValueError("temperature_bounds_K must be strictly increasing")

    @property
    def residence_time_s(self) -> float:
        return self.volume_L / self.volumetric_flow_L_s

    def rate_constant_s_inv(self, temperature_K: float) -> float:
        _positive(temperature_K, "temperature_K")
        return self.arrhenius_A_s_inv * exp(
            -self.arrhenius_Ea_J_per_mol / (8.31446261815324 * temperature_K)
        )

    def steady_concentration_a_mol_l(self, temperature_K: float) -> float:
        k = self.rate_constant_s_inv(temperature_K)
        return self.feed_concentration_A_mol_L / (1.0 + k * self.residence_time_s)

    def steady_conversion(self, temperature_K: float) -> float:
        return 1.0 - (
            self.steady_concentration_a_mol_l(temperature_K)
            / self.feed_concentration_A_mol_L
        )

    def reaction_rate_mol_l_s(self, temperature_K: float) -> float:
        return self.rate_constant_s_inv(temperature_K) * self.steady_concentration_a_mol_l(
            temperature_K
        )

    def heat_generation_w(self, temperature_K: float) -> float:
        return (
            -self.delta_h_J_per_mol
            * self.volume_L
            * self.reaction_rate_mol_l_s(temperature_K)
        )

    def heat_removal_w(self, temperature_K: float) -> float:
        return self.rho_cp_J_per_L_K * self.volumetric_flow_L_s * (
            temperature_K - self.feed_temperature_K
        ) + self.ua_W_per_K * (temperature_K - self.coolant_temperature_K)

    def energy_residual_w(self, temperature_K: float) -> float:
        return self.heat_generation_w(temperature_K) - self.heat_removal_w(temperature_K)

    def network(self) -> ReactionNetworkSpec:
        reactant_id, product_id = self.species_ids
        return ReactionNetworkSpec(
            network_id=f"{self.case_id}_network",
            species=(
                SpeciesSpec(reactant_id, "C2H4O2"),
                SpeciesSpec(product_id, "C2H4O2"),
            ),
            reactions=(
                ReactionSpec.from_equation(
                    reaction_id="exothermic_conversion",
                    equation=f"{reactant_id} => {product_id}",
                    rate_law=RateLawSpec(
                        "exothermic_conversion_rate",
                        "arrhenius",
                        {
                            "A": self.arrhenius_A_s_inv,
                            "Ea_J_per_mol": self.arrhenius_Ea_J_per_mol,
                        },
                    ),
                    delta_h_J_per_mol=self.delta_h_J_per_mol,
                ),
            ),
            metadata={"reference_case": self.case_id},
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "case_id": self.case_id,
            "feed_concentration_A_mol_L": self.feed_concentration_A_mol_L,
            "volumetric_flow_L_s": self.volumetric_flow_L_s,
            "volume_L": self.volume_L,
            "feed_temperature_K": self.feed_temperature_K,
            "coolant_temperature_K": self.coolant_temperature_K,
            "ua_W_per_K": self.ua_W_per_K,
            "rho_cp_J_per_L_K": self.rho_cp_J_per_L_K,
            "delta_h_J_per_mol": self.delta_h_J_per_mol,
            "arrhenius_A_s_inv": self.arrhenius_A_s_inv,
            "arrhenius_Ea_J_per_mol": self.arrhenius_Ea_J_per_mol,
            "temperature_bounds_K": list(self.temperature_bounds_K),
            "residence_time_s": self.residence_time_s,
            "species_ids": list(self.species_ids),
        }


@dataclass(frozen=True)
class CSTRSteadyStatePoint:
    temperature_K: float
    concentration_A_mol_L: float
    concentration_P_mol_L: float
    conversion: float
    reaction_rate_mol_l_s: float
    heat_generation_w: float
    heat_removal_w: float
    residual_W: float
    eigenvalues: tuple[complex, ...]
    stability: SteadyStateStability

    def to_dict(self) -> dict[str, object]:
        return {
            "temperature_K": self.temperature_K,
            "concentration_A_mol_L": self.concentration_A_mol_L,
            "concentration_P_mol_L": self.concentration_P_mol_L,
            "conversion": self.conversion,
            "reaction_rate_mol_l_s": self.reaction_rate_mol_l_s,
            "heat_generation_w": self.heat_generation_w,
            "heat_removal_w": self.heat_removal_w,
            "residual_W": self.residual_W,
            "eigenvalues": [
                {"real": value.real, "imag": value.imag}
                for value in self.eigenvalues
            ],
            "stability": self.stability,
        }


@dataclass(frozen=True)
class CSTRMultiplicityResult:
    case_id: str
    spec: CSTRMultiplicitySpec
    steady_states: tuple[CSTRSteadyStatePoint, ...]
    scan_step_K: float
    residual_tolerance_W: float

    @property
    def temperatures_k(self) -> tuple[float, ...]:
        return tuple(point.temperature_K for point in self.steady_states)

    @property
    def stable_temperatures_k(self) -> tuple[float, ...]:
        return tuple(
            point.temperature_K
            for point in self.steady_states
            if point.stability == "stable"
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "case_id": self.case_id,
            "spec": self.spec.to_dict(),
            "steady_states": [point.to_dict() for point in self.steady_states],
            "temperatures_k": list(self.temperatures_k),
            "stable_temperatures_k": list(self.stable_temperatures_k),
            "scan_step_K": self.scan_step_K,
            "residual_tolerance_W": self.residual_tolerance_W,
        }


def cstr_multiple_steady_state_reference_case() -> CSTRMultiplicitySpec:
    """Return a ChemWorld-owned exothermic CSTR multiplicity case."""

    return CSTRMultiplicitySpec(
        case_id="cstr_exothermic_multiplicity_reference",
        feed_concentration_A_mol_L=1.0,
        volumetric_flow_L_s=0.1,
        volume_L=500.0,
        feed_temperature_K=300.0,
        coolant_temperature_K=270.0,
        ua_W_per_K=1.0,
        rho_cp_J_per_L_K=4180.0,
        delta_h_J_per_mol=-300_000.0,
        arrhenius_A_s_inv=1.0e11,
        arrhenius_Ea_J_per_mol=95_000.0,
        temperature_bounds_K=(290.0, 430.0),
    )


def solve_cstr_multiple_steady_states(
    spec: CSTRMultiplicitySpec | None = None,
    *,
    temperature_step_K: float = 0.25,
    residual_tolerance_W: float = 1e-6,
    stability_tolerance_s_inv: float = 1e-9,
) -> CSTRMultiplicityResult:
    """Solve scalar CSTR energy-balance roots and classify local stability."""

    case = cstr_multiple_steady_state_reference_case() if spec is None else spec
    _positive(temperature_step_K, "temperature_step_K")
    if residual_tolerance_W < 0:
        raise ValueError("residual_tolerance_W cannot be negative")
    if stability_tolerance_s_inv < 0:
        raise ValueError("stability_tolerance_s_inv cannot be negative")

    low, high = case.temperature_bounds_K
    grid = [
        float(value)
        for value in np.arange(low, high + 0.5 * temperature_step_K, temperature_step_K)
    ]
    if grid[-1] < high:
        grid.append(high)
    residuals = [case.energy_residual_w(temperature) for temperature in grid]
    roots = _bracketed_scalar_roots(
        lambda temperature: case.energy_residual_w(temperature),
        tuple(grid),
        tuple(residuals),
    )
    points = tuple(
        _cstr_steady_state_point(
            case,
            temperature_K=root,
            residual_tolerance_W=residual_tolerance_W,
            stability_tolerance_s_inv=stability_tolerance_s_inv,
        )
        for root in roots
    )
    return CSTRMultiplicityResult(
        case_id=case.case_id,
        spec=case,
        steady_states=points,
        scan_step_K=temperature_step_K,
        residual_tolerance_W=residual_tolerance_W,
    )


def _bracketed_scalar_roots(
    func: Callable[[float], float],
    grid: tuple[float, ...],
    residuals: tuple[float, ...],
    *,
    dedup_tolerance_K: float = 1e-6,
) -> tuple[float, ...]:
    roots: list[float] = []
    for left, right, residual_left, residual_right in zip(
        grid,
        grid[1:],
        residuals,
        residuals[1:],
        strict=False,
    ):
        if residual_left == 0.0:
            roots.append(left)
        if residual_left * residual_right < 0.0:
            roots.append(brentq(func, left, right))
    if residuals[-1] == 0.0:
        roots.append(grid[-1])
    roots.sort()
    deduped: list[float] = []
    for root in roots:
        if not deduped or abs(root - deduped[-1]) > dedup_tolerance_K:
            deduped.append(root)
    return tuple(deduped)


def _cstr_steady_state_point(
    spec: CSTRMultiplicitySpec,
    *,
    temperature_K: float,
    residual_tolerance_W: float,
    stability_tolerance_s_inv: float,
) -> CSTRSteadyStatePoint:
    residual = spec.energy_residual_w(temperature_K)
    if abs(residual) > residual_tolerance_W:
        raise RuntimeError(
            "CSTR steady-state root residual exceeded tolerance: "
            f"{residual} W at {temperature_K} K"
        )
    concentration_a = spec.steady_concentration_a_mol_l(temperature_K)
    concentration_p = spec.feed_concentration_A_mol_L - concentration_a
    eigenvalues = tuple(
        complex(value)
        for value in np.linalg.eigvals(_cstr_dynamic_jacobian(spec, temperature_K))
    )
    max_real = max(value.real for value in eigenvalues)
    if max_real < -stability_tolerance_s_inv:
        stability: SteadyStateStability = "stable"
    elif max_real > stability_tolerance_s_inv:
        stability = "unstable"
    else:
        stability = "marginal"
    return CSTRSteadyStatePoint(
        temperature_K=temperature_K,
        concentration_A_mol_L=concentration_a,
        concentration_P_mol_L=concentration_p,
        conversion=spec.steady_conversion(temperature_K),
        reaction_rate_mol_l_s=spec.reaction_rate_mol_l_s(temperature_K),
        heat_generation_w=spec.heat_generation_w(temperature_K),
        heat_removal_w=spec.heat_removal_w(temperature_K),
        residual_W=residual,
        eigenvalues=eigenvalues,
        stability=stability,
    )


def _cstr_dynamic_jacobian(
    spec: CSTRMultiplicitySpec,
    temperature_K: float,
) -> np.ndarray:
    k = spec.rate_constant_s_inv(temperature_K)
    dkdT = k * spec.arrhenius_Ea_J_per_mol / (
        8.31446261815324 * temperature_K * temperature_K
    )
    concentration_a = spec.steady_concentration_a_mol_l(temperature_K)
    residence_inverse = spec.volumetric_flow_L_s / spec.volume_L
    heat_factor = -spec.delta_h_J_per_mol / spec.rho_cp_J_per_L_K
    heat_removal_s_inv = spec.ua_W_per_K / (spec.rho_cp_J_per_L_K * spec.volume_L)
    return np.array(
        [
            [-residence_inverse - k, -concentration_a * dkdT],
            [
                heat_factor * k,
                (
                    -residence_inverse
                    - heat_removal_s_inv
                    + heat_factor * concentration_a * dkdT
                ),
            ],
        ],
        dtype=float,
    )


__all__ = [
    "CSTRMultiplicityResult",
    "CSTRMultiplicitySpec",
    "CSTRSteadyStatePoint",
    "cstr_multiple_steady_state_reference_case",
    "solve_cstr_multiple_steady_states",
]
