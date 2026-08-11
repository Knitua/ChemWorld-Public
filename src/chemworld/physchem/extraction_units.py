"""Activity-corrected multistage liquid-liquid extraction trains."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from math import exp, isfinite, log

from chemworld.physchem.equilibrium import ActivityModelSpec, activity_coefficients


@dataclass(frozen=True)
class DistributionCoefficientModelSpec:
    """Thermodynamic contract for composition-dependent distribution ratios."""

    model_id: str
    component_ids: tuple[str, ...]
    intrinsic_partition_coefficients: dict[str, float]
    provenance_id: str
    aqueous_activity_model: ActivityModelSpec | None = None
    organic_activity_model: ActivityModelSpec | None = None

    def __post_init__(self) -> None:
        if not self.model_id:
            raise ValueError("model_id cannot be empty")
        if not self.component_ids or len(set(self.component_ids)) != len(self.component_ids):
            raise ValueError("component_ids must be nonempty and unique")
        if any(not component_id for component_id in self.component_ids):
            raise ValueError("component_ids cannot contain empty ids")
        if set(self.intrinsic_partition_coefficients) != set(self.component_ids):
            raise ValueError("intrinsic_partition_coefficients must exactly match component_ids")
        if any(
            value <= 0.0 or not isfinite(value)
            for value in self.intrinsic_partition_coefficients.values()
        ):
            raise ValueError("intrinsic_partition_coefficients must be positive and finite")
        if not self.provenance_id:
            raise ValueError("provenance_id cannot be empty")
        for phase_name, model in (
            ("aqueous", self.aqueous_activity_model),
            ("organic", self.organic_activity_model),
        ):
            if model is not None and set(model.component_ids) != set(self.component_ids):
                raise ValueError(f"{phase_name}_activity_model components must match component_ids")

    def to_dict(self) -> dict[str, object]:
        return {
            "model_id": self.model_id,
            "component_ids": list(self.component_ids),
            "intrinsic_partition_coefficients": dict(self.intrinsic_partition_coefficients),
            "provenance_id": self.provenance_id,
            "aqueous_activity_model_id": (
                None
                if self.aqueous_activity_model is None
                else self.aqueous_activity_model.model_id
            ),
            "organic_activity_model_id": (
                None
                if self.organic_activity_model is None
                else self.organic_activity_model.model_id
            ),
        }


@dataclass(frozen=True)
class ExtractionStageReport:
    stage_id: str
    mode: str
    aqueous_volume_L: float
    organic_volume_L: float
    input_amounts_mol: dict[str, float]
    input_organic_amounts_mol: dict[str, float]
    organic_amounts_mol: dict[str, float]
    aqueous_amounts_mol: dict[str, float]
    distribution_coefficients: dict[str, float]
    aqueous_activity_coefficients: dict[str, float]
    organic_activity_coefficients: dict[str, float]
    recovery_to_organic: dict[str, float]
    entrained_amounts_mol: dict[str, float]
    entrained_aqueous_volume_L: float
    stage_efficiency: float
    iterations: int
    converged: bool
    material_balance_error_mol: float
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "stage_id": self.stage_id,
            "mode": self.mode,
            "aqueous_volume_L": self.aqueous_volume_L,
            "organic_volume_L": self.organic_volume_L,
            "input_amounts_mol": dict(self.input_amounts_mol),
            "input_organic_amounts_mol": dict(self.input_organic_amounts_mol),
            "organic_amounts_mol": dict(self.organic_amounts_mol),
            "aqueous_amounts_mol": dict(self.aqueous_amounts_mol),
            "distribution_coefficients": dict(self.distribution_coefficients),
            "aqueous_activity_coefficients": dict(self.aqueous_activity_coefficients),
            "organic_activity_coefficients": dict(self.organic_activity_coefficients),
            "recovery_to_organic": dict(self.recovery_to_organic),
            "entrained_amounts_mol": dict(self.entrained_amounts_mol),
            "entrained_aqueous_volume_L": self.entrained_aqueous_volume_L,
            "stage_efficiency": self.stage_efficiency,
            "iterations": self.iterations,
            "converged": self.converged,
            "material_balance_error_mol": self.material_balance_error_mol,
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class ExtractionTrainResult:
    model_id: str
    distribution_model_id: str
    provenance_id: str
    temperature_K: float
    target_component: str
    feed_amounts_mol: dict[str, float]
    outlets: dict[str, dict[str, float]]
    stage_reports: tuple[ExtractionStageReport, ...]
    target_recovery: float
    target_purity: float
    impurity_rejection: float
    entrained_aqueous_volume_L: float
    material_balance_error_mol: float
    cost: float
    risk: float
    warnings: tuple[str, ...] = ()

    def outlet(self, outlet_id: str) -> dict[str, float]:
        return dict(self.outlets[outlet_id])

    def to_dict(self) -> dict[str, object]:
        return {
            "model_id": self.model_id,
            "distribution_model_id": self.distribution_model_id,
            "provenance_id": self.provenance_id,
            "temperature_K": self.temperature_K,
            "target_component": self.target_component,
            "feed_amounts_mol": dict(self.feed_amounts_mol),
            "outlets": {key: dict(value) for key, value in self.outlets.items()},
            "stage_reports": [report.to_dict() for report in self.stage_reports],
            "target_recovery": self.target_recovery,
            "target_purity": self.target_purity,
            "impurity_rejection": self.impurity_rejection,
            "entrained_aqueous_volume_L": self.entrained_aqueous_volume_L,
            "material_balance_error_mol": self.material_balance_error_mol,
            "cost": self.cost,
            "risk": self.risk,
            "warnings": list(self.warnings),
        }


def activity_corrected_extraction_train(
    feed_amounts_mol: Mapping[str, float],
    *,
    distribution_model: DistributionCoefficientModelSpec,
    target_component: str,
    aqueous_volume_L: float,
    organic_volume_L: float,
    extraction_stages: int = 1,
    extraction_stage_efficiency: float = 1.0,
    extraction_entrainment_fraction: float = 0.0,
    wash_aqueous_volumes_L: Sequence[float] = (),
    wash_stage_efficiency: float = 1.0,
    wash_entrainment_fraction: float = 0.0,
    temperature_K: float = 298.15,
    tolerance: float = 1.0e-10,
    max_iterations: int = 100,
) -> ExtractionTrainResult:
    """Run fresh-solvent extraction stages followed by aqueous wash stages."""

    feed = _validated_amounts(feed_amounts_mol, distribution_model.component_ids)
    if target_component not in feed:
        raise ValueError("target_component must be present in the feed")
    if feed[target_component] <= 0.0:
        raise ValueError("target_component must have a positive feed amount")
    _positive_finite(aqueous_volume_L, "aqueous_volume_L")
    _positive_finite(organic_volume_L, "organic_volume_L")
    _positive_finite(temperature_K, "temperature_K")
    _positive_finite(tolerance, "tolerance")
    if extraction_stages <= 0:
        raise ValueError("extraction_stages must be positive")
    if max_iterations <= 0:
        raise ValueError("max_iterations must be positive")
    _fraction(extraction_stage_efficiency, "extraction_stage_efficiency", closed=True)
    _fraction(extraction_entrainment_fraction, "extraction_entrainment_fraction")
    _fraction(wash_stage_efficiency, "wash_stage_efficiency", closed=True)
    _fraction(wash_entrainment_fraction, "wash_entrainment_fraction")
    wash_volumes = tuple(float(value) for value in wash_aqueous_volumes_L)
    for value in wash_volumes:
        _positive_finite(value, "wash_aqueous_volumes_L")

    reports: list[ExtractionStageReport] = []
    raffinate = dict(feed)
    combined_extract = dict.fromkeys(distribution_model.component_ids, 0.0)
    for index in range(1, extraction_stages + 1):
        report = _equilibrium_contact_stage(
            stage_id=f"extraction_{index}",
            mode="extraction",
            total_amounts_mol=raffinate,
            input_organic_amounts_mol=dict.fromkeys(distribution_model.component_ids, 0.0),
            aqueous_volume_L=aqueous_volume_L,
            organic_volume_L=organic_volume_L,
            stage_efficiency=extraction_stage_efficiency,
            entrainment_fraction=extraction_entrainment_fraction,
            distribution_model=distribution_model,
            temperature_K=temperature_K,
            tolerance=tolerance,
            max_iterations=max_iterations,
        )
        reports.append(report)
        combined_extract = _add(combined_extract, report.organic_amounts_mol)
        raffinate = report.aqueous_amounts_mol

    outlets: dict[str, dict[str, float]] = {"raffinate": dict(raffinate)}
    washed_extract = combined_extract
    combined_organic_volume_L = extraction_stages * organic_volume_L
    for index, wash_volume_L in enumerate(wash_volumes, start=1):
        report = _equilibrium_contact_stage(
            stage_id=f"wash_{index}",
            mode="wash",
            total_amounts_mol=washed_extract,
            input_organic_amounts_mol=washed_extract,
            aqueous_volume_L=wash_volume_L,
            organic_volume_L=combined_organic_volume_L,
            stage_efficiency=wash_stage_efficiency,
            entrainment_fraction=wash_entrainment_fraction,
            distribution_model=distribution_model,
            temperature_K=temperature_K,
            tolerance=tolerance,
            max_iterations=max_iterations,
        )
        reports.append(report)
        washed_extract = report.organic_amounts_mol
        outlets[f"wash_{index}"] = report.aqueous_amounts_mol
    outlets["extract"] = dict(washed_extract)

    material_error = _balance_error(feed, outlets)
    target_recovery = washed_extract[target_component] / feed[target_component]
    extract_total = sum(washed_extract.values())
    target_purity = (
        0.0 if extract_total <= 0.0 else washed_extract[target_component] / extract_total
    )
    feed_impurity = sum(amount for key, amount in feed.items() if key != target_component)
    extract_impurity = sum(
        amount for key, amount in washed_extract.items() if key != target_component
    )
    impurity_rejection = 1.0 if feed_impurity <= 0.0 else 1.0 - extract_impurity / feed_impurity
    entrained_volume = sum(report.entrained_aqueous_volume_L for report in reports)
    warnings = [
        f"{report.stage_id}:distribution_iteration_not_converged"
        for report in reports
        if not report.converged
    ]
    if entrained_volume > 0.05 * (extraction_stages * aqueous_volume_L + sum(wash_volumes)):
        warnings.append("aqueous_entrainment_exceeds_five_percent_of_contact_volume")
    cost = (
        0.35 * extraction_stages
        + 0.08 * extraction_stages * organic_volume_L
        + 0.20 * len(wash_volumes)
        + 0.04 * sum(wash_volumes)
    )
    risk = min(
        1.0,
        0.04 * extraction_stages
        + 0.02 * len(wash_volumes)
        + 0.5 * max(extraction_entrainment_fraction, wash_entrainment_fraction),
    )
    return ExtractionTrainResult(
        model_id="activity_corrected_extraction_train_v1",
        distribution_model_id=distribution_model.model_id,
        provenance_id=distribution_model.provenance_id,
        temperature_K=temperature_K,
        target_component=target_component,
        feed_amounts_mol=feed,
        outlets=outlets,
        stage_reports=tuple(reports),
        target_recovery=target_recovery,
        target_purity=target_purity,
        impurity_rejection=impurity_rejection,
        entrained_aqueous_volume_L=entrained_volume,
        material_balance_error_mol=material_error,
        cost=cost,
        risk=risk,
        warnings=tuple(warnings),
    )


def _equilibrium_contact_stage(
    *,
    stage_id: str,
    mode: str,
    total_amounts_mol: Mapping[str, float],
    input_organic_amounts_mol: Mapping[str, float],
    aqueous_volume_L: float,
    organic_volume_L: float,
    stage_efficiency: float,
    entrainment_fraction: float,
    distribution_model: DistributionCoefficientModelSpec,
    temperature_K: float,
    tolerance: float,
    max_iterations: int,
) -> ExtractionStageReport:
    component_ids = distribution_model.component_ids
    distribution = dict(distribution_model.intrinsic_partition_coefficients)
    aqueous_gamma = dict.fromkeys(component_ids, 1.0)
    organic_gamma = dict.fromkeys(component_ids, 1.0)
    converged = False
    iterations = 0
    equilibrium_organic = dict.fromkeys(component_ids, 0.0)
    for iteration in range(1, max_iterations + 1):
        iterations = iteration
        equilibrium_organic = {
            key: total_amounts_mol[key]
            * distribution[key]
            * organic_volume_L
            / (distribution[key] * organic_volume_L + aqueous_volume_L)
            for key in component_ids
        }
        equilibrium_aqueous = {
            key: total_amounts_mol[key] - equilibrium_organic[key] for key in component_ids
        }
        aqueous_composition = _composition(equilibrium_aqueous, component_ids)
        organic_composition = _composition(equilibrium_organic, component_ids)
        aqueous_gamma = _phase_activity_coefficients(
            distribution_model.aqueous_activity_model,
            aqueous_composition,
            temperature_K,
        )
        organic_gamma = _phase_activity_coefficients(
            distribution_model.organic_activity_model,
            organic_composition,
            temperature_K,
        )
        updated = {
            key: distribution_model.intrinsic_partition_coefficients[key]
            * aqueous_gamma[key]
            / organic_gamma[key]
            for key in component_ids
        }
        error = max(abs(log(updated[key] / distribution[key])) for key in component_ids)
        distribution = {
            key: exp(0.5 * (log(distribution[key]) + log(updated[key]))) for key in component_ids
        }
        if error <= tolerance:
            distribution = updated
            converged = True
            break

    equilibrium_organic = {
        key: total_amounts_mol[key]
        * distribution[key]
        * organic_volume_L
        / (distribution[key] * organic_volume_L + aqueous_volume_L)
        for key in component_ids
    }
    organic = {
        key: input_organic_amounts_mol[key]
        + stage_efficiency * (equilibrium_organic[key] - input_organic_amounts_mol[key])
        for key in component_ids
    }
    aqueous = {key: total_amounts_mol[key] - organic[key] for key in component_ids}
    entrained = {key: entrainment_fraction * aqueous[key] for key in component_ids}
    organic = {key: organic[key] + entrained[key] for key in component_ids}
    aqueous = {key: aqueous[key] - entrained[key] for key in component_ids}
    recovery = {
        key: (0.0 if total_amounts_mol[key] <= 0.0 else organic[key] / total_amounts_mol[key])
        for key in component_ids
    }
    warnings: list[str] = []
    if not converged:
        warnings.append("distribution_iteration_not_converged")
    if entrainment_fraction > 0.0:
        warnings.append("aqueous_entrainment_present")
    return ExtractionStageReport(
        stage_id=stage_id,
        mode=mode,
        aqueous_volume_L=aqueous_volume_L,
        organic_volume_L=organic_volume_L,
        input_amounts_mol=dict(total_amounts_mol),
        input_organic_amounts_mol=dict(input_organic_amounts_mol),
        organic_amounts_mol=organic,
        aqueous_amounts_mol=aqueous,
        distribution_coefficients=distribution,
        aqueous_activity_coefficients=aqueous_gamma,
        organic_activity_coefficients=organic_gamma,
        recovery_to_organic=recovery,
        entrained_amounts_mol=entrained,
        entrained_aqueous_volume_L=entrainment_fraction * aqueous_volume_L,
        stage_efficiency=stage_efficiency,
        iterations=iterations,
        converged=converged,
        material_balance_error_mol=_balance_error(
            total_amounts_mol,
            {"organic": organic, "aqueous": aqueous},
        ),
        warnings=tuple(warnings),
    )


def _phase_activity_coefficients(
    model: ActivityModelSpec | None,
    composition: Mapping[str, float],
    temperature_K: float,
) -> dict[str, float]:
    if model is None:
        return dict.fromkeys(composition, 1.0)
    return activity_coefficients(model, composition, temperature_K=temperature_K)


def _validated_amounts(
    values: Mapping[str, float],
    component_ids: tuple[str, ...],
) -> dict[str, float]:
    if set(values) != set(component_ids):
        raise ValueError("feed_amounts_mol must exactly match distribution components")
    result = {key: float(values[key]) for key in component_ids}
    if any(value < 0.0 or not isfinite(value) for value in result.values()):
        raise ValueError("feed_amounts_mol must contain finite nonnegative values")
    if sum(result.values()) <= 0.0:
        raise ValueError("feed_amounts_mol must contain positive total material")
    return result


def _composition(
    amounts: Mapping[str, float],
    component_ids: tuple[str, ...],
) -> dict[str, float]:
    total = sum(amounts.values())
    if total <= 0.0:
        return {key: 1.0 / len(component_ids) for key in component_ids}
    return {key: amounts[key] / total for key in component_ids}


def _add(left: Mapping[str, float], right: Mapping[str, float]) -> dict[str, float]:
    keys = tuple(left) + tuple(key for key in right if key not in left)
    return {key: left.get(key, 0.0) + right.get(key, 0.0) for key in keys}


def _balance_error(
    feed: Mapping[str, float],
    outlets: Mapping[str, Mapping[str, float]],
) -> float:
    return max(
        (abs(feed[key] - sum(outlet.get(key, 0.0) for outlet in outlets.values())) for key in feed),
        default=0.0,
    )


def _positive_finite(value: float, field_name: str) -> None:
    if value <= 0.0 or not isfinite(value):
        raise ValueError(f"{field_name} must be positive and finite")


def _fraction(value: float, field_name: str, *, closed: bool = False) -> None:
    upper_valid = value <= 1.0 if closed else value < 1.0
    if value < 0.0 or not upper_valid or not isfinite(value):
        interval = "[0, 1]" if closed else "[0, 1)"
        raise ValueError(f"{field_name} must be finite and in {interval}")


__all__ = [
    "DistributionCoefficientModelSpec",
    "ExtractionStageReport",
    "ExtractionTrainResult",
    "activity_corrected_extraction_train",
]
