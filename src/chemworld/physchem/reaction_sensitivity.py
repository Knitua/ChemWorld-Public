"""Finite-difference sensitivity helpers for reaction networks."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from math import exp, isfinite, sqrt
from typing import Any, Literal, Protocol

from chemworld.physchem.reaction_network_specs import ReactionSpec
from chemworld.physchem.reaction_rate_laws import (
    positive_reaction_parameter,
    with_reaction_parameter,
)


class BatchIntegrationLike(Protocol):
    final_amounts_mol: dict[str, float]


class SensitivityNetworkLike(Protocol):
    network_id: str

    @property
    def species_ids(self) -> tuple[str, ...]: ...

    @property
    def reactions(self) -> tuple[ReactionSpec, ...]: ...

    def integrate_batch(
        self,
        initial_amounts_mol: Mapping[str, float],
        *,
        volume_L: float,
        temperature_K: float,
        duration_s: float,
        species_thermo: Mapping[str, Any] | None = None,
    ) -> BatchIntegrationLike: ...


@dataclass(frozen=True)
class ReactionSensitivityEntry:
    """Finite-difference sensitivity for one kinetic parameter."""

    reaction_id: str
    parameter_name: str
    observable: str
    baseline_parameter_value: float
    perturbation_log_step: float
    baseline_observable_value: float
    plus_observable_value: float
    minus_observable_value: float
    derivative_dobservable_dln_parameter: float
    normalized_sensitivity: float | None
    local_observable_std: float
    local_normalized_std: float | None

    @property
    def parameter_id(self) -> str:
        return f"{self.reaction_id}.{self.parameter_name}"

    @property
    def direction(self) -> Literal["positive", "negative", "near_zero"]:
        if abs(self.derivative_dobservable_dln_parameter) < 1e-15:
            return "near_zero"
        if self.derivative_dobservable_dln_parameter > 0:
            return "positive"
        return "negative"

    @property
    def rank_score(self) -> float:
        if self.normalized_sensitivity is not None:
            return abs(self.normalized_sensitivity)
        return abs(self.derivative_dobservable_dln_parameter)

    def to_dict(self) -> dict[str, object]:
        return {
            "parameter_id": self.parameter_id,
            "reaction_id": self.reaction_id,
            "parameter_name": self.parameter_name,
            "observable": self.observable,
            "baseline_parameter_value": self.baseline_parameter_value,
            "perturbation_log_step": self.perturbation_log_step,
            "baseline_observable_value": self.baseline_observable_value,
            "plus_observable_value": self.plus_observable_value,
            "minus_observable_value": self.minus_observable_value,
            "derivative_dobservable_dln_parameter": (self.derivative_dobservable_dln_parameter),
            "normalized_sensitivity": self.normalized_sensitivity,
            "local_observable_std": self.local_observable_std,
            "local_normalized_std": self.local_normalized_std,
            "direction": self.direction,
            "rank_score": self.rank_score,
        }


@dataclass(frozen=True)
class ReactionSensitivityReport:
    """JSON-friendly local kinetic sensitivity report."""

    network_id: str
    observable: str
    observable_species_id: str
    baseline_observable_value: float
    volume_L: float
    temperature_K: float
    duration_s: float
    perturbation_log_step: float
    relative_parameter_uncertainty: float
    entries: tuple[ReactionSensitivityEntry, ...]
    method: str = "central_finite_difference_log_parameter"

    @property
    def uncertainty_summary(self) -> dict[str, float | None]:
        variance = sum(entry.local_observable_std**2 for entry in self.entries)
        observable_std = float(sqrt(variance))
        normalized_variance = sum(
            entry.local_normalized_std**2
            for entry in self.entries
            if entry.local_normalized_std is not None
        )
        normalized_std: float | None
        if abs(self.baseline_observable_value) > 1e-15:
            normalized_std = float(sqrt(normalized_variance))
        else:
            normalized_std = None
        return {
            "relative_parameter_uncertainty": self.relative_parameter_uncertainty,
            "observable_std_estimate": observable_std,
            "normalized_std_estimate": normalized_std,
        }

    @property
    def nondegeneracy_summary(self) -> dict[str, object]:
        """Report whether declared perturbations produce distinguishable responses."""

        threshold = 1.0e-10
        informative = tuple(
            entry
            for entry in self.entries
            if abs(entry.derivative_dobservable_dln_parameter) > threshold
        )
        rounded_magnitudes = {
            round(abs(entry.derivative_dobservable_dln_parameter), 10) for entry in informative
        }
        return {
            "threshold_dobservable_dln_parameter": threshold,
            "parameter_count": len(self.entries),
            "informative_parameter_count": len(informative),
            "distinct_response_magnitude_count": len(rounded_magnitudes),
            "positive_response_count": sum(
                entry.derivative_dobservable_dln_parameter > threshold for entry in informative
            ),
            "negative_response_count": sum(
                entry.derivative_dobservable_dln_parameter < -threshold for entry in informative
            ),
            "passed": bool(informative),
        }

    def ranked_entries(self, limit: int | None = None) -> tuple[ReactionSensitivityEntry, ...]:
        ranked = tuple(
            sorted(
                self.entries,
                key=lambda entry: entry.rank_score,
                reverse=True,
            )
        )
        if limit is None:
            return ranked
        if limit < 0:
            raise ValueError("limit cannot be negative")
        return ranked[:limit]

    def explanation_ranking(self, limit: int = 3) -> tuple[dict[str, object], ...]:
        return tuple(
            {
                "rank": index + 1,
                "parameter_id": entry.parameter_id,
                "reaction_id": entry.reaction_id,
                "parameter_name": entry.parameter_name,
                "direction": entry.direction,
                "normalized_sensitivity": entry.normalized_sensitivity,
                "interpretation": (
                    f"{entry.parameter_id} has a {entry.direction} local effect "
                    f"on {self.observable}."
                ),
            }
            for index, entry in enumerate(self.ranked_entries(limit))
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "network_id": self.network_id,
            "observable": self.observable,
            "observable_species_id": self.observable_species_id,
            "baseline_observable_value": self.baseline_observable_value,
            "volume_L": self.volume_L,
            "temperature_K": self.temperature_K,
            "duration_s": self.duration_s,
            "perturbation_log_step": self.perturbation_log_step,
            "relative_parameter_uncertainty": self.relative_parameter_uncertainty,
            "method": self.method,
            "entries": [entry.to_dict() for entry in self.entries],
            "uncertainty_summary": self.uncertainty_summary,
            "nondegeneracy_summary": self.nondegeneracy_summary,
            "explanation_ranking": list(self.explanation_ranking()),
        }


def finite_difference_reaction_sensitivities(
    network: SensitivityNetworkLike,
    initial_amounts_mol: Mapping[str, float],
    *,
    volume_L: float,
    temperature_K: float,
    duration_s: float,
    observable_species_id: str,
    parameters: Sequence[tuple[str, str]] | None = None,
    perturbation_log_step: float = 1e-4,
    relative_parameter_uncertainty: float = 0.10,
    species_thermo: Mapping[str, Any] | None = None,
) -> ReactionSensitivityReport:
    """Return local finite-difference kinetic sensitivities.

    Sensitivities use Cantera-style normalized response coefficients:

    ``S = (1/y) d y / d ln(p)``

    for positive rate multiplier-like parameters. The implementation is a
    deterministic ChemWorld-local central finite difference and is intended for
    benchmark explanation/model-learning hooks, not for replacing adjoint
    sensitivity solvers.
    """

    if observable_species_id not in network.species_ids:
        raise ValueError(f"Unknown observable species: {observable_species_id}")
    if perturbation_log_step <= 0 or not isfinite(perturbation_log_step):
        raise ValueError("perturbation_log_step must be finite and positive")
    if perturbation_log_step > 0.1:
        raise ValueError("perturbation_log_step is too large for local sensitivity")
    if relative_parameter_uncertainty < 0 or not isfinite(relative_parameter_uncertainty):
        raise ValueError("relative_parameter_uncertainty must be finite and nonnegative")
    candidates = (
        tuple(parameters)
        if parameters is not None
        else kinetic_sensitivity_parameter_candidates(network)
    )
    if not candidates:
        raise ValueError("No positive kinetic sensitivity parameters were found")

    baseline = network.integrate_batch(
        initial_amounts_mol,
        volume_L=volume_L,
        temperature_K=temperature_K,
        duration_s=duration_s,
        species_thermo=species_thermo,
    )
    baseline_value = baseline.final_amounts_mol[observable_species_id]
    entries: list[ReactionSensitivityEntry] = []
    factor = exp(perturbation_log_step)
    for reaction_id, parameter_name in candidates:
        baseline_parameter = positive_reaction_parameter(
            network,
            reaction_id,
            parameter_name,
        )
        plus_network = with_reaction_parameter(
            network,
            reaction_id,
            parameter_name,
            baseline_parameter * factor,
        )
        minus_network = with_reaction_parameter(
            network,
            reaction_id,
            parameter_name,
            baseline_parameter / factor,
        )
        plus = plus_network.integrate_batch(
            initial_amounts_mol,
            volume_L=volume_L,
            temperature_K=temperature_K,
            duration_s=duration_s,
            species_thermo=species_thermo,
        )
        minus = minus_network.integrate_batch(
            initial_amounts_mol,
            volume_L=volume_L,
            temperature_K=temperature_K,
            duration_s=duration_s,
            species_thermo=species_thermo,
        )
        plus_value = plus.final_amounts_mol[observable_species_id]
        minus_value = minus.final_amounts_mol[observable_species_id]
        derivative = (plus_value - minus_value) / (2.0 * perturbation_log_step)
        normalized: float | None = None
        local_normalized_std: float | None = None
        if abs(baseline_value) > 1e-15:
            normalized = derivative / baseline_value
            local_normalized_std = abs(normalized) * relative_parameter_uncertainty
        entries.append(
            ReactionSensitivityEntry(
                reaction_id=reaction_id,
                parameter_name=parameter_name,
                observable=f"final_amount:{observable_species_id}",
                baseline_parameter_value=baseline_parameter,
                perturbation_log_step=perturbation_log_step,
                baseline_observable_value=baseline_value,
                plus_observable_value=plus_value,
                minus_observable_value=minus_value,
                derivative_dobservable_dln_parameter=derivative,
                normalized_sensitivity=normalized,
                local_observable_std=abs(derivative) * relative_parameter_uncertainty,
                local_normalized_std=local_normalized_std,
            )
        )
    return ReactionSensitivityReport(
        network_id=network.network_id,
        observable=f"final_amount:{observable_species_id}",
        observable_species_id=observable_species_id,
        baseline_observable_value=baseline_value,
        volume_L=volume_L,
        temperature_K=temperature_K,
        duration_s=duration_s,
        perturbation_log_step=perturbation_log_step,
        relative_parameter_uncertainty=relative_parameter_uncertainty,
        entries=tuple(entries),
    )


def kinetic_sensitivity_parameter_candidates(
    network: SensitivityNetworkLike,
    *,
    parameter_names: Sequence[str] = ("k", "A", "A_reverse", "K_eq", "vmax", "Km"),
) -> tuple[tuple[str, str], ...]:
    """Return positive multiplier-like kinetic parameters for sensitivities."""

    allowed = set(parameter_names)
    candidates: list[tuple[str, str]] = []
    for reaction in network.reactions:
        for parameter_name, value in reaction.rate_law.parameters.items():
            if parameter_name not in allowed:
                continue
            if isinstance(value, int | float | str):
                numeric = float(value)
                if numeric > 0 and isfinite(numeric):
                    candidates.append((reaction.reaction_id, parameter_name))
    return tuple(candidates)


__all__ = [
    "BatchIntegrationLike",
    "ReactionSensitivityEntry",
    "ReactionSensitivityReport",
    "SensitivityNetworkLike",
    "finite_difference_reaction_sensitivities",
    "kinetic_sensitivity_parameter_candidates",
]
