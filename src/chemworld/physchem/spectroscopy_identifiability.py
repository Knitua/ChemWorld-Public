"""Deterministic identifiability audits for synthetic instrument signals."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from math import isfinite, sqrt
from typing import Any

import numpy as np

from chemworld.physchem.maturity import MaturityLevel, ModelCard, ValidationEvidence
from chemworld.physchem.spectroscopy import SpectralMeasurement

CHEMICALS_COMMIT = "82faef900dcf2b48537c31bcf1ab56c35bb79a1e"
RMG_PY_COMMIT = "b858624649205fc8ae08aec601c4c216e9edcee0"


@dataclass(frozen=True)
class SpectralIdentifiabilitySpec:
    """Acceptance thresholds for one pairwise signal audit."""

    min_replicates: int = 3
    max_within_state_rmse: float = 0.05
    min_between_state_rmse: float = 0.01
    min_separation_ratio: float = 3.0
    noise_floor: float = 1.0e-12

    def __post_init__(self) -> None:
        if self.min_replicates < 2:
            raise ValueError("min_replicates must be at least two")
        for field_name in (
            "max_within_state_rmse",
            "min_between_state_rmse",
            "min_separation_ratio",
            "noise_floor",
        ):
            value = float(getattr(self, field_name))
            if not isfinite(value) or value <= 0.0:
                raise ValueError(f"{field_name} must be finite and positive")

    def to_dict(self) -> dict[str, float | int]:
        return {
            "min_replicates": self.min_replicates,
            "max_within_state_rmse": self.max_within_state_rmse,
            "min_between_state_rmse": self.min_between_state_rmse,
            "min_separation_ratio": self.min_separation_ratio,
            "noise_floor": self.noise_floor,
        }


@dataclass(frozen=True)
class SpectralIdentifiabilityReport:
    """Public, species-agnostic evidence for a pair of instrument states."""

    instrument_id: str
    point_count: int
    reference_replicate_count: int
    alternative_replicate_count: int
    reference_within_state_rmse: float
    alternative_within_state_rmse: float
    pooled_within_state_rmse: float
    between_state_rmse: float
    separation_ratio: float
    reference_detected_peak_count: int
    alternative_detected_peak_count: int
    replicate_stable: bool
    states_distinct: bool
    identifiable: bool
    reference_signal_sha256: str
    alternative_signal_sha256: str
    thresholds: SpectralIdentifiabilitySpec
    warnings: tuple[str, ...]
    provenance: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "chemworld-spectral-identifiability-0.1",
            "instrument_id": self.instrument_id,
            "point_count": self.point_count,
            "reference_replicate_count": self.reference_replicate_count,
            "alternative_replicate_count": self.alternative_replicate_count,
            "reference_within_state_rmse": self.reference_within_state_rmse,
            "alternative_within_state_rmse": self.alternative_within_state_rmse,
            "pooled_within_state_rmse": self.pooled_within_state_rmse,
            "between_state_rmse": self.between_state_rmse,
            "separation_ratio": self.separation_ratio,
            "reference_detected_peak_count": self.reference_detected_peak_count,
            "alternative_detected_peak_count": self.alternative_detected_peak_count,
            "replicate_stable": self.replicate_stable,
            "states_distinct": self.states_distinct,
            "identifiable": self.identifiable,
            "reference_signal_sha256": self.reference_signal_sha256,
            "alternative_signal_sha256": self.alternative_signal_sha256,
            "thresholds": self.thresholds.to_dict(),
            "warnings": list(self.warnings),
            "provenance": list(self.provenance),
            "public_boundary": (
                "signal-level aggregate only; no species identities, hidden amounts, "
                "peak assignments, or evaluator truth"
            ),
        }


def evaluate_spectral_identifiability(
    reference: SpectralMeasurement,
    alternative: SpectralMeasurement,
    *,
    spec: SpectralIdentifiabilitySpec | None = None,
) -> SpectralIdentifiabilityReport:
    """Compare two independently replicated public raw-signal states."""

    policy = SpectralIdentifiabilitySpec() if spec is None else spec
    _validate_pair(reference, alternative, policy)
    reference_replicates = np.asarray(reference.replicate_signals, dtype=float)
    alternative_replicates = np.asarray(alternative.replicate_signals, dtype=float)
    reference_mean = np.mean(reference_replicates, axis=0)
    alternative_mean = np.mean(alternative_replicates, axis=0)
    reference_within = _replicate_rmse(reference_replicates, reference_mean)
    alternative_within = _replicate_rmse(alternative_replicates, alternative_mean)
    pooled = sqrt((reference_within**2 + alternative_within**2) / 2.0)
    between = _rmse(reference_mean, alternative_mean)
    ratio = between / max(pooled, policy.noise_floor)
    replicate_stable = max(reference_within, alternative_within) <= (policy.max_within_state_rmse)
    states_distinct = (
        between >= policy.min_between_state_rmse and ratio >= policy.min_separation_ratio
    )
    warnings: list[str] = []
    if not replicate_stable:
        warnings.append("replicate_instability")
    if between < policy.min_between_state_rmse:
        warnings.append("between_state_effect_below_minimum")
    if ratio < policy.min_separation_ratio:
        warnings.append("separation_ratio_below_minimum")
    return SpectralIdentifiabilityReport(
        instrument_id=reference.instrument_id,
        point_count=len(reference.axis),
        reference_replicate_count=len(reference.replicate_signals),
        alternative_replicate_count=len(alternative.replicate_signals),
        reference_within_state_rmse=reference_within,
        alternative_within_state_rmse=alternative_within,
        pooled_within_state_rmse=pooled,
        between_state_rmse=between,
        separation_ratio=ratio,
        reference_detected_peak_count=_detected_peak_count(reference),
        alternative_detected_peak_count=_detected_peak_count(alternative),
        replicate_stable=replicate_stable,
        states_distinct=states_distinct,
        identifiable=replicate_stable and states_distinct,
        reference_signal_sha256=_measurement_signal_hash(reference),
        alternative_signal_sha256=_measurement_signal_hash(alternative),
        thresholds=policy,
        warnings=tuple(warnings),
        provenance=(
            "paired public raw-signal replicate RMSE and between-state RMSE",
            "analytical separation ratio = between-state RMSE / pooled within-state RMSE",
            (
                f"chemicals {CHEMICALS_COMMIT}: property/data reference only; "
                "not treated as an instrument simulator"
            ),
            (
                f"RMG-Py {RMG_PY_COMMIT}: chemistry schema reference only; "
                "not treated as an instrument simulator"
            ),
        ),
    )


def spectroscopy_identifiability_model_card() -> ModelCard:
    """Return the model card for the signal-level identifiability audit."""

    return ModelCard(
        model_id="chemworld_spectral_identifiability_audit_vnext",
        module_id="spectroscopy_instruments",
        title="Replicate Stability And Pairwise Spectral Identifiability Audit",
        maturity=MaturityLevel.REFERENCE_VALIDATED,
        summary=(
            "An offline diagnostic comparing within-state replicate variation "
            "against the raw-signal difference between two instrument states."
        ),
        equations=(
            "RMSE_within = sqrt(mean((replicate - state_mean)^2))",
            "RMSE_between = sqrt(mean((mean_a - mean_b)^2))",
            "separation_ratio = RMSE_between / max(RMSE_pooled, noise_floor)",
        ),
        assumptions=(
            "both measurements use the same instrument, axis, and preprocessing",
            "replicates are independent draws from the declared synthetic noise model",
            "pairwise separation is assessed on public raw-signal arrays only",
        ),
        validity_limits=(
            "pairwise diagnostic rather than a multi-class identifiability proof",
            "does not establish chemical selectivity or real-instrument validity",
            "thresholds are benchmark audit policy and must be reported with results",
        ),
        failure_modes=(
            "fewer than two replicates is rejected",
            "instrument, axis, point-count, or nonfinite-signal mismatch is rejected",
            "unstable replicates or weak separation return explicit warnings",
        ),
        units={
            "signal": "instrument-normalized signal",
            "rmse": "instrument-normalized signal",
            "separation_ratio": "dimensionless",
        },
        reference_reading=(
            "Analytical pooled within-state and between-state RMSE identities.",
            (
                f"chemicals {CHEMICALS_COMMIT} and RMG-Py {RMG_PY_COMMIT} are "
                "recorded as non-instrument reference boundaries."
            ),
            "ChemWorld spectroscopy.py supplies the audited replicate signals.",
        ),
        validation_evidence=(
            ValidationEvidence(
                evidence_id="spectral-identifiability-reference-cases",
                evidence_type="analytical_and_unit_test",
                description=(
                    "Fixtures cover HPLC stable/distinct behavior, UV-vis insufficient "
                    "default separation, censored instability, mismatches, and determinism."
                ),
                status="implemented",
                command_or_path="tests/test_spectroscopy_identifiability.py",
                tolerance="explicit policy thresholds and exact deterministic hashes",
            ),
        ),
        model_limit_notes=(
            "Reference-validated applies to the audit calculation, not the synthetic spectra.",
            "Task-level identifiability still requires a complete scenario matrix review.",
        ),
        intended_use=(
            "instrument regression gates",
            "task-level signal distinguishability audits",
            "replicate-noise policy review before World Law vNext integration",
        ),
    )


def _validate_pair(
    reference: SpectralMeasurement,
    alternative: SpectralMeasurement,
    spec: SpectralIdentifiabilitySpec,
) -> None:
    if reference.instrument_id != alternative.instrument_id:
        raise ValueError("measurements must use the same instrument_id")
    if reference.axis_key != alternative.axis_key or reference.signal_key != alternative.signal_key:
        raise ValueError("measurements must use the same public signal contract")
    if len(reference.axis) != len(alternative.axis) or not np.array_equal(
        np.asarray(reference.axis),
        np.asarray(alternative.axis),
    ):
        raise ValueError("measurements must use identical axes")
    for label, measurement in (("reference", reference), ("alternative", alternative)):
        if len(measurement.replicate_signals) < spec.min_replicates:
            raise ValueError(
                f"{label} measurement requires at least {spec.min_replicates} replicates"
            )
        replicates = np.asarray(measurement.replicate_signals, dtype=float)
        if replicates.ndim != 2 or replicates.shape[1] != len(measurement.axis):
            raise ValueError(f"{label} replicate signals do not match the public axis")
        if not np.all(np.isfinite(replicates)):
            raise ValueError(f"{label} replicate signals must be finite")


def _replicate_rmse(replicates: np.ndarray, mean_signal: np.ndarray) -> float:
    return float(np.sqrt(np.mean((replicates - mean_signal) ** 2)))


def _rmse(left: np.ndarray, right: np.ndarray) -> float:
    return float(np.sqrt(np.mean((left - right) ** 2)))


def _detected_peak_count(measurement: SpectralMeasurement) -> int:
    return sum(bool(peak.get("detected", False)) for peak in measurement.peaks)


def _measurement_signal_hash(measurement: SpectralMeasurement) -> str:
    payload = {
        "instrument_id": measurement.instrument_id,
        "axis_key": measurement.axis_key,
        "signal_key": measurement.signal_key,
        "axis": list(measurement.axis),
        "replicate_signals": [list(signal) for signal in measurement.replicate_signals],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


__all__ = [
    "CHEMICALS_COMMIT",
    "RMG_PY_COMMIT",
    "SpectralIdentifiabilityReport",
    "SpectralIdentifiabilitySpec",
    "evaluate_spectral_identifiability",
    "spectroscopy_identifiability_model_card",
]
