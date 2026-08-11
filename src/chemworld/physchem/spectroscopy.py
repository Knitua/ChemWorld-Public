"""Local spectroscopy and chromatography signal synthesis for ChemWorld."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from itertools import pairwise
from math import isfinite, log10, sqrt
from typing import Any, Literal

import numpy as np

from chemworld.physchem.mechanism_library import MechanismScenarioCard
from chemworld.physchem.reaction_network import ReactionNetworkSpec
from chemworld.physchem.spectroscopy_cards import spectroscopy_model_cards

PeakShape = Literal["gaussian", "lorentzian"]


@dataclass(frozen=True)
class CalibrationCurve:
    slope: float
    intercept: float = 0.0
    lower_limit: float = 0.0
    upper_limit: float = 1.0e6
    noise_relative: float = 0.03

    def __post_init__(self) -> None:
        if self.slope <= 0.0 or not isfinite(self.slope):
            raise ValueError("Calibration slope must be finite and positive")
        if self.lower_limit < 0.0 or self.upper_limit <= self.lower_limit:
            raise ValueError("Calibration limits must be nonnegative and increasing")
        if self.noise_relative < 0.0:
            raise ValueError("Calibration noise cannot be negative")

    def response(self, concentration_mol_L: float) -> float:
        concentration = float(np.clip(concentration_mol_L, self.lower_limit, self.upper_limit))
        return self.intercept + self.slope * concentration

    def estimate_concentration(self, response: float) -> float:
        concentration = (float(response) - self.intercept) / self.slope
        return float(np.clip(concentration, self.lower_limit, self.upper_limit))

    def to_dict(self) -> dict[str, float]:
        return {
            "slope": self.slope,
            "intercept": self.intercept,
            "lower_limit": self.lower_limit,
            "upper_limit": self.upper_limit,
            "noise_relative": self.noise_relative,
        }


@dataclass(frozen=True)
class BeerLambertBandSpec:
    species_id: str
    wavelength_nm: float
    molar_absorptivity_L_mol_cm: float
    path_length_cm: float = 1.0
    dilution_factor: float = 1.0
    bandwidth_nm: float = 32.0
    blank_absorbance: float = 0.0
    detection_limit_mol_L: float = 0.0
    noise_absorbance: float = 0.001
    assignment: str = "uvvis_band"
    group: str = "other"

    def __post_init__(self) -> None:
        if not self.species_id.strip():
            raise ValueError("species_id cannot be empty")
        if self.wavelength_nm <= 0.0 or not isfinite(self.wavelength_nm):
            raise ValueError("wavelength_nm must be finite and positive")
        if (
            self.molar_absorptivity_L_mol_cm <= 0.0
            or not isfinite(self.molar_absorptivity_L_mol_cm)
        ):
            raise ValueError("molar_absorptivity_L_mol_cm must be finite and positive")
        if self.path_length_cm <= 0.0 or self.dilution_factor <= 0.0:
            raise ValueError("path_length_cm and dilution_factor must be positive")
        if self.bandwidth_nm <= 0.0:
            raise ValueError("bandwidth_nm must be positive")
        if self.blank_absorbance < 0.0 or self.detection_limit_mol_L < 0.0:
            raise ValueError("blank_absorbance and detection_limit_mol_L cannot be negative")
        if self.noise_absorbance < 0.0:
            raise ValueError("noise_absorbance cannot be negative")

    @property
    def effective_slope_absorbance_per_mol_l(self) -> float:
        return (
            self.molar_absorptivity_L_mol_cm
            * self.path_length_cm
            / self.dilution_factor
        )

    def absorbance(self, concentration_mol_L: float) -> float:
        return beer_lambert_absorbance(
            concentration_mol_L / self.dilution_factor,
            molar_absorptivity_L_mol_cm=self.molar_absorptivity_L_mol_cm,
            path_length_cm=self.path_length_cm,
            blank_absorbance=self.blank_absorbance,
        )

    def calibration_curve(self) -> CalibrationCurve:
        return CalibrationCurve(
            slope=self.effective_slope_absorbance_per_mol_l,
            intercept=self.blank_absorbance,
            lower_limit=self.detection_limit_mol_L,
            upper_limit=5.0,
            noise_relative=max(self.noise_absorbance, 1.0e-12)
            / max(self.effective_slope_absorbance_per_mol_l, 1.0e-12),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "model_id": "beer_lambert_uvvis",
            "species_id": self.species_id,
            "wavelength_nm": self.wavelength_nm,
            "molar_absorptivity_L_mol_cm": self.molar_absorptivity_L_mol_cm,
            "path_length_cm": self.path_length_cm,
            "dilution_factor": self.dilution_factor,
            "bandwidth_nm": self.bandwidth_nm,
            "blank_absorbance": self.blank_absorbance,
            "detection_limit_mol_L": self.detection_limit_mol_L,
            "noise_absorbance": self.noise_absorbance,
            "effective_slope_absorbance_per_mol_L": (
                self.effective_slope_absorbance_per_mol_l
            ),
            "assignment": self.assignment,
            "group": self.group,
        }


@dataclass(frozen=True)
class BeerLambertCalibrationResult:
    species_id: str
    path_length_cm: float
    dilution_factor: float
    concentrations_mol_L: tuple[float, ...]
    absorbances: tuple[float, ...]
    fitted_slope_absorbance_per_mol_L: float
    intercept_absorbance: float
    molar_absorptivity_L_mol_cm: float
    residual_std_absorbance: float
    slope_std_error: float
    r_squared: float
    detection_limit_mol_L: float
    quantitation_limit_mol_L: float

    def to_dict(self) -> dict[str, object]:
        return {
            "species_id": self.species_id,
            "path_length_cm": self.path_length_cm,
            "dilution_factor": self.dilution_factor,
            "concentrations_mol_L": list(self.concentrations_mol_L),
            "absorbances": list(self.absorbances),
            "fitted_slope_absorbance_per_mol_L": self.fitted_slope_absorbance_per_mol_L,
            "intercept_absorbance": self.intercept_absorbance,
            "molar_absorptivity_L_mol_cm": self.molar_absorptivity_L_mol_cm,
            "residual_std_absorbance": self.residual_std_absorbance,
            "slope_std_error": self.slope_std_error,
            "r_squared": self.r_squared,
            "detection_limit_mol_L": self.detection_limit_mol_L,
            "quantitation_limit_mol_L": self.quantitation_limit_mol_L,
        }


@dataclass(frozen=True)
class IRFunctionalGroupBandSpec:
    group_id: str
    assignment: str
    center_cm_inv: float
    width_cm_inv: float
    relative_intensity: float
    shape: PeakShape = "gaussian"
    detection_limit_mol_L: float = 0.004
    provenance: str = "ChemWorld curated functional-group IR slice"

    def __post_init__(self) -> None:
        if not self.group_id.strip() or not self.assignment.strip():
            raise ValueError("IR group_id and assignment cannot be empty")
        if self.center_cm_inv <= 0.0 or not isfinite(self.center_cm_inv):
            raise ValueError("IR center_cm_inv must be finite and positive")
        if self.width_cm_inv <= 0.0 or not isfinite(self.width_cm_inv):
            raise ValueError("IR width_cm_inv must be finite and positive")
        if self.relative_intensity <= 0.0 or not isfinite(self.relative_intensity):
            raise ValueError("IR relative_intensity must be finite and positive")
        if self.detection_limit_mol_L < 0.0:
            raise ValueError("IR detection_limit_mol_L cannot be negative")
        if self.shape not in {"gaussian", "lorentzian"}:
            raise ValueError("IR shape must be gaussian or lorentzian")

    def to_feature(
        self,
        *,
        species_id: str,
        role: str,
        formula: str,
        warning: str | None = None,
    ) -> SpectralFeatureSpec:
        metadata: dict[str, object] = self.to_dict()
        metadata.update(
            {
                "model_id": "ir_functional_group_bands",
                "species_id": species_id,
                "role": role,
                "formula": formula,
                "warning": warning,
            }
        )
        role_gain = {
            "target": 1.15,
            "reactant": 0.95,
            "byproduct": 1.05,
            "degradation": 1.20,
            "catalyst": 0.75,
            "other": 0.85,
        }.get(role, 0.85)
        slope = self.relative_intensity * role_gain
        return SpectralFeatureSpec(
            species_id=species_id,
            instrument_id="ir",
            center=self.center_cm_inv,
            width=self.width_cm_inv,
            response_factor=slope,
            detection_limit_mol_L=self.detection_limit_mol_L,
            assignment=f"{species_id}_{self.group_id}_{self.assignment}",
            group=role,
            shape=self.shape,
            calibration=CalibrationCurve(
                slope=slope,
                lower_limit=self.detection_limit_mol_L,
                upper_limit=5.0,
                noise_relative=0.055 if self.group_id != "hydroxyl_broad" else 0.075,
            ),
            metadata=metadata,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "group_id": self.group_id,
            "assignment": self.assignment,
            "center_cm_inv": self.center_cm_inv,
            "width_cm_inv": self.width_cm_inv,
            "relative_intensity": self.relative_intensity,
            "shape": self.shape,
            "detection_limit_mol_L": self.detection_limit_mol_L,
            "provenance": self.provenance,
        }


@dataclass(frozen=True)
class IRBandAssignmentReport:
    species_id: str
    role: str
    formula: str
    element_counts: dict[str, int]
    bands: tuple[IRFunctionalGroupBandSpec, ...]
    interference_pairs: tuple[tuple[str, str], ...]
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "species_id": self.species_id,
            "role": self.role,
            "formula": self.formula,
            "element_counts": dict(self.element_counts),
            "bands": [band.to_dict() for band in self.bands],
            "interference_pairs": [list(pair) for pair in self.interference_pairs],
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class ChromatographyMethodSpec:
    instrument_id: str
    dead_time_min: float
    theoretical_plates: float
    retention_factor_by_group: Mapping[str, float]
    response_factor_by_group: Mapping[str, float]
    detection_limit_mol_L: float
    noise_relative: float = 0.025
    reference_peak_width_min: float | None = None

    def __post_init__(self) -> None:
        if self.instrument_id not in {"hplc", "gc"}:
            raise ValueError("instrument_id must be 'hplc' or 'gc'")
        if self.dead_time_min <= 0.0 or not isfinite(self.dead_time_min):
            raise ValueError("dead_time_min must be finite and positive")
        if self.theoretical_plates <= 0.0 or not isfinite(self.theoretical_plates):
            raise ValueError("theoretical_plates must be finite and positive")
        if self.detection_limit_mol_L < 0.0 or self.noise_relative < 0.0:
            raise ValueError("detection limit and noise must be nonnegative")
        if not self.retention_factor_by_group:
            raise ValueError("retention_factor_by_group cannot be empty")
        for group, retention_factor in self.retention_factor_by_group.items():
            if not group.strip():
                raise ValueError("retention-factor groups cannot be empty")
            if retention_factor < 0.0 or not isfinite(retention_factor):
                raise ValueError("retention factors must be finite and nonnegative")
        for group, response in self.response_factor_by_group.items():
            if not group.strip():
                raise ValueError("response-factor groups cannot be empty")
            if response <= 0.0 or not isfinite(response):
                raise ValueError("response factors must be finite and positive")
        if self.reference_peak_width_min is not None and self.reference_peak_width_min <= 0.0:
            raise ValueError("reference_peak_width_min must be positive if supplied")

    def retention_factor(self, group: str, species_id: str) -> float:
        base = self.retention_factor_by_group.get(
            group,
            self.retention_factor_by_group.get("other", 1.0),
        )
        perturbation = _stable_offset(f"{self.instrument_id}:{species_id}:k", scale=0.18)
        return max(base + perturbation, 0.02)

    def response_factor(self, group: str) -> float:
        return self.response_factor_by_group.get(
            group,
            self.response_factor_by_group.get("other", 500.0),
        )

    def feature_metadata(self, *, species_id: str, group: str) -> dict[str, object]:
        retention_factor = self.retention_factor(group, species_id)
        retention_time = chromatographic_retention_time(
            dead_time_min=self.dead_time_min,
            retention_factor=retention_factor,
        )
        baseline_width = chromatographic_baseline_peak_width(
            retention_time_min=retention_time,
            theoretical_plates=self.theoretical_plates,
        )
        gaussian_sigma = baseline_width / 4.0
        return {
            "model_id": "chromatography_retention_plate",
            "instrument_id": self.instrument_id,
            "species_id": species_id,
            "group": group,
            "dead_time_min": self.dead_time_min,
            "retention_factor": retention_factor,
            "retention_time_min": retention_time,
            "theoretical_plates": self.theoretical_plates,
            "baseline_width_min": baseline_width,
            "gaussian_sigma_min": gaussian_sigma,
            "detection_limit_mol_L": self.detection_limit_mol_L,
            "reference_peak_width_min": self.reference_peak_width_min,
        }


@dataclass(frozen=True)
class ChromatographyCalibrationResult:
    species_id: str
    instrument_id: str
    dead_time_min: float
    retention_times_min: tuple[float, ...]
    baseline_widths_min: tuple[float, ...]
    retention_factor_mean: float
    retention_factor_std: float
    retention_time_mean_min: float
    retention_time_std_min: float
    theoretical_plates_mean: float
    theoretical_plates_std: float

    def to_dict(self) -> dict[str, object]:
        return {
            "species_id": self.species_id,
            "instrument_id": self.instrument_id,
            "dead_time_min": self.dead_time_min,
            "retention_times_min": list(self.retention_times_min),
            "baseline_widths_min": list(self.baseline_widths_min),
            "retention_factor_mean": self.retention_factor_mean,
            "retention_factor_std": self.retention_factor_std,
            "retention_time_mean_min": self.retention_time_mean_min,
            "retention_time_std_min": self.retention_time_std_min,
            "theoretical_plates_mean": self.theoretical_plates_mean,
            "theoretical_plates_std": self.theoretical_plates_std,
        }


@dataclass(frozen=True)
class SpectralFeatureSpec:
    species_id: str
    instrument_id: str
    center: float
    width: float
    response_factor: float
    detection_limit_mol_L: float
    assignment: str
    group: str
    shape: PeakShape = "gaussian"
    calibration: CalibrationCurve = field(
        default_factory=lambda: CalibrationCurve(slope=1.0),
    )
    metadata: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.width <= 0.0 or not isfinite(self.width):
            raise ValueError("Feature width must be finite and positive")
        if self.response_factor <= 0.0 or not isfinite(self.response_factor):
            raise ValueError("Feature response_factor must be finite and positive")
        if self.detection_limit_mol_L < 0.0:
            raise ValueError("Feature detection limit cannot be negative")

    def to_dict(self) -> dict[str, object]:
        return {
            "species_id": self.species_id,
            "instrument_id": self.instrument_id,
            "center": self.center,
            "width": self.width,
            "response_factor": self.response_factor,
            "detection_limit_mol_L": self.detection_limit_mol_L,
            "assignment": self.assignment,
            "group": self.group,
            "shape": self.shape,
            "calibration": self.calibration.to_dict(),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class InstrumentSignalSpec:
    instrument_id: str
    kind: str
    axis_key: str
    signal_key: str
    axis_unit: str
    axis_start: float
    axis_stop: float
    points: int
    baseline: float
    baseline_drift: float
    noise_std: float
    features: tuple[SpectralFeatureSpec, ...]
    detector_gain: float = 1.0
    normalize: bool = True
    signal_mode: Literal["positive", "transmittance"] = "positive"

    def __post_init__(self) -> None:
        if self.axis_stop <= self.axis_start:
            raise ValueError("Signal axis_stop must be greater than axis_start")
        if self.points < 5:
            raise ValueError("Signal axis must contain at least five points")
        if self.baseline < 0.0 or self.noise_std < 0.0:
            raise ValueError("Baseline and noise must be nonnegative")
        if self.detector_gain <= 0.0 or not isfinite(self.detector_gain):
            raise ValueError("detector_gain must be finite and positive")

    @property
    def axis(self) -> np.ndarray:
        return np.linspace(self.axis_start, self.axis_stop, self.points, dtype=float)

    def to_dict(self) -> dict[str, object]:
        return {
            "instrument_id": self.instrument_id,
            "kind": self.kind,
            "axis_key": self.axis_key,
            "signal_key": self.signal_key,
            "axis_unit": self.axis_unit,
            "axis_start": self.axis_start,
            "axis_stop": self.axis_stop,
            "points": self.points,
            "baseline": self.baseline,
            "baseline_drift": self.baseline_drift,
            "noise_std": self.noise_std,
            "detector_gain": self.detector_gain,
            "normalize": self.normalize,
            "signal_mode": self.signal_mode,
            "features": [feature.to_dict() for feature in self.features],
        }


@dataclass(frozen=True)
class SpectralMeasurement:
    instrument_id: str
    kind: str
    axis_key: str
    signal_key: str
    axis: tuple[float, ...]
    signal: tuple[float, ...]
    replicate_signals: tuple[tuple[float, ...], ...]
    peaks: tuple[dict[str, object], ...]
    processed_estimates: dict[str, float]
    uncertainty: dict[str, float]
    metadata: dict[str, object]

    def to_dict(self) -> dict[str, Any]:
        """Return the internal validation representation.

        This representation intentionally retains feature identities and model
        diagnostics for reference tests.  Runtime observations must use
        :meth:`to_public_dict`, which removes those evaluator-only fields.
        """

        return {
            "kind": self.kind,
            self.axis_key: list(self.axis),
            self.signal_key: list(self.signal),
            "replicate_signals": [list(signal) for signal in self.replicate_signals],
            "replicate_count": len(self.replicate_signals),
            "peaks": [dict(peak) for peak in self.peaks],
            "processed_estimates": dict(self.processed_estimates),
            "uncertainty": dict(self.uncertainty),
            "metadata": dict(self.metadata),
        }

    def to_public_dict(self, *, sample_volume_L: float) -> dict[str, Any]:
        """Return a leakage-safe, layered synthetic-instrument observation.

        Stable anonymous analyte and peak labels preserve longitudinal
        comparison without revealing mechanism species, provider identity, or
        evaluator truth.  The numerical raw trace remains available so an
        agent must interpret evidence rather than receive a hidden answer.
        """

        if sample_volume_L <= 0.0 or not isfinite(sample_volume_L):
            raise ValueError("sample_volume_L must be finite and positive")
        species_order = sorted(
            {str(peak["species_id"]) for peak in self.peaks},
            key=lambda species_id: min(
                _as_float(peak["center"])
                for peak in self.peaks
                if str(peak["species_id"]) == species_id
            ),
        )
        aliases = {
            species_id: f"analyte_{index:02d}"
            for index, species_id in enumerate(species_order, start=1)
        }
        public_peaks: list[dict[str, object]] = []
        assignments: list[dict[str, object]] = []
        missing: list[dict[str, object]] = []
        calibration: dict[str, dict[str, object]] = {}
        processed: dict[str, float | None] = {}
        public_uncertainty: dict[str, float | None] = {}
        for index, peak in enumerate(self.peaks, start=1):
            peak_id = f"peak_{index:03d}"
            species_id = str(peak["species_id"])
            analyte_id = aliases[species_id]
            detected = bool(peak["detected"])
            lod = _as_float(peak["detection_limit_mol_L"])
            loq = 10.0 / 3.3 * lod
            estimate = _as_float(peak["estimated_concentration_mol_L"])
            saturated = estimate >= 5.0
            uncertainty_key = f"{species_id}_std_mol_L"
            standard_uncertainty = self.uncertainty.get(uncertainty_key)
            error_draws = self.metadata.get("public_estimate_error_z", {})
            error_z = (
                _as_float(error_draws.get(species_id, 0.0))
                if isinstance(error_draws, Mapping)
                else 0.0
            )
            standard_error = 0.0 if standard_uncertainty is None else standard_uncertainty
            reported_estimate = float(np.clip(estimate + error_z * standard_error, 0.0, 5.0))
            relative_error = standard_error / max(estimate, 1.0e-12)
            reported_area = max(
                _as_float(peak["area"]) * (1.0 + error_z * relative_error),
                0.0,
            )
            public_peaks.append(
                {
                    "peak_id": peak_id,
                    "assignment": _public_assignment_label(str(peak["group"])),
                    "center": _as_float(peak["center"]),
                    "width": _as_float(peak["width"]),
                    "area": round(reported_area, 6),
                    "detected": detected,
                    "saturated": saturated,
                    "overlap_group": peak.get("overlap_group"),
                }
            )
            assignments.append(
                {
                    "peak_id": peak_id,
                    "analyte_id": analyte_id,
                    "species_id": species_id,
                    "status": (
                        "above_linear_range"
                        if saturated
                        else "anonymous_calibrated_feature"
                        if detected
                        else "below_lod"
                    ),
                    "confidence": 0.70 if detected and peak.get("overlap_group") else 0.92,
                }
            )
            calibration.setdefault(
                analyte_id,
                {
                    "method": _public_calibration_method(self.instrument_id),
                    "lod_mol_L": round(lod, 9),
                    "loq_mol_L": round(loq, 9),
                    "linear_range_mol_L": [round(lod, 9), 5.0],
                    "saturation_policy": "clip_and_flag_above_linear_range",
                },
            )
            estimate_key = f"{analyte_id}_concentration_mol_L"
            uncertainty_public_key = f"{analyte_id}_standard_uncertainty_mol_L"
            processed[estimate_key] = round(reported_estimate, 9) if detected else None
            public_uncertainty[uncertainty_public_key] = (
                None if standard_uncertainty is None else round(float(standard_uncertainty), 9)
            )
            if not detected:
                missing.append(
                    {
                        "analyte_id": analyte_id,
                        "reason": "below_lod",
                        "reported_value": None,
                    }
                )
            elif saturated:
                missing.append(
                    {
                        "analyte_id": analyte_id,
                        "reason": "above_linear_range",
                        "reported_value": round(reported_estimate, 9),
                    }
                )
        public_metadata = {
            "axis_unit": str(self.metadata.get("axis_unit", "a.u.")),
            "baseline": _as_float(self.metadata.get("baseline", 0.0)),
            "baseline_drift": _as_float(self.metadata.get("baseline_drift", 0.0)),
            "noise_model": "seeded_independent_gaussian",
            "detector_gain": _as_float(self.metadata.get("detector_gain", 1.0)),
            "synthetic": True,
            "real_sample_prediction": False,
            "boundary_note": (
                "Synthetic benchmark evidence; not a real-instrument or empirical sample spectrum."
            ),
        }
        return {
            "schema_version": "chemworld-public-synthetic-signal-0.2",
            "kind": self.kind,
            "instrument_id": self.instrument_id,
            self.axis_key: list(self.axis),
            self.signal_key: list(self.signal),
            "replicate_signals": [list(signal) for signal in self.replicate_signals],
            "replicate_count": len(self.replicate_signals),
            "sample_state": {
                "sample_basis_volume_L": round(float(sample_volume_L), 9),
                "physical_state": "virtual_liquid_sample",
                "matrix": "task_public_aggregate",
                "preparation": "declared_instrument_calibration",
            },
            "axis": {
                "key": self.axis_key,
                "unit": public_metadata["axis_unit"],
                "point_count": len(self.axis),
            },
            "raw_signal": {
                "key": self.signal_key,
                "unit": _signal_unit(self.instrument_id),
                "normalization": (
                    "none" if self.instrument_id in {"uvvis", "ir"} else "maximum_response"
                ),
            },
            "peaks": public_peaks,
            "assignments": assignments,
            "processed_estimates": processed,
            "uncertainty": public_uncertainty,
            "calibration": calibration,
            "missingness": {
                "policy": "below_lod_is_null; failed_measurement_has_no_signal_packet",
                "entries": missing,
            },
            "metadata": public_metadata,
        }


def build_signal_spec_from_card(
    instrument_id: str,
    card: MechanismScenarioCard,
    network: ReactionNetworkSpec,
) -> InstrumentSignalSpec:
    return build_signal_spec(
        instrument_id,
        network.species_ids,
        target_species=card.target_species,
        impurity_species=card.impurity_species,
        formulas={species.species_id: species.formula for species in network.species},
    )


def build_signal_spec(
    instrument_id: str,
    species_ids: Sequence[str],
    *,
    target_species: Sequence[str] = (),
    impurity_species: Sequence[str] = (),
    formulas: Mapping[str, str] | None = None,
) -> InstrumentSignalSpec:
    features = default_feature_specs(
        instrument_id,
        species_ids,
        target_species=target_species,
        impurity_species=impurity_species,
        formulas={} if formulas is None else formulas,
    )
    if instrument_id == "hplc":
        return InstrumentSignalSpec(
            instrument_id="hplc",
            kind="hplc_chromatogram",
            axis_key="time_min",
            signal_key="intensity",
            axis_unit="min",
            axis_start=0.0,
            axis_stop=6.0,
            points=241,
            baseline=0.010,
            baseline_drift=0.004,
            noise_std=0.002,
            features=features,
        )
    if instrument_id == "gc":
        return InstrumentSignalSpec(
            instrument_id="gc",
            kind="gc_chromatogram",
            axis_key="time_min",
            signal_key="intensity",
            axis_unit="min",
            axis_start=0.0,
            axis_stop=4.0,
            points=201,
            baseline=0.008,
            baseline_drift=0.003,
            noise_std=0.0025,
            features=features,
        )
    if instrument_id == "uvvis":
        return InstrumentSignalSpec(
            instrument_id="uvvis",
            kind="uvvis_spectrum",
            axis_key="wavelength_nm",
            signal_key="absorbance",
            axis_unit="nm",
            axis_start=320.0,
            axis_stop=760.0,
            points=221,
            baseline=0.020,
            baseline_drift=0.006,
            noise_std=0.0015,
            features=features,
            normalize=False,
        )
    if instrument_id == "ir":
        return InstrumentSignalSpec(
            instrument_id="ir",
            kind="ir_spectrum",
            axis_key="wavenumber_cm-1",
            signal_key="transmittance",
            axis_unit="cm-1",
            axis_start=400.0,
            axis_stop=4000.0,
            points=241,
            baseline=0.0,
            baseline_drift=0.002,
            noise_std=0.001,
            features=features,
            normalize=False,
            signal_mode="transmittance",
        )
    if instrument_id == "nmr":
        return InstrumentSignalSpec(
            instrument_id="nmr",
            kind="nmr_1h_spectrum",
            axis_key="chemical_shift_ppm",
            signal_key="intensity",
            axis_unit="ppm",
            axis_start=0.0,
            axis_stop=12.0,
            points=241,
            baseline=0.004,
            baseline_drift=0.001,
            noise_std=0.001,
            features=features,
        )
    raise ValueError(f"Unsupported instrument_id={instrument_id!r}")


def beer_lambert_absorbance(
    concentration_mol_L: float,
    *,
    molar_absorptivity_L_mol_cm: float,
    path_length_cm: float = 1.0,
    blank_absorbance: float = 0.0,
) -> float:
    if concentration_mol_L < 0.0 or not isfinite(concentration_mol_L):
        raise ValueError("concentration_mol_L must be finite and nonnegative")
    if (
        molar_absorptivity_L_mol_cm <= 0.0
        or not isfinite(molar_absorptivity_L_mol_cm)
    ):
        raise ValueError("molar_absorptivity_L_mol_cm must be finite and positive")
    if path_length_cm <= 0.0 or not isfinite(path_length_cm):
        raise ValueError("path_length_cm must be finite and positive")
    if blank_absorbance < 0.0 or not isfinite(blank_absorbance):
        raise ValueError("blank_absorbance must be finite and nonnegative")
    return (
        blank_absorbance
        + molar_absorptivity_L_mol_cm * path_length_cm * concentration_mol_L
    )


def potentiometric_ph(*, hydrogen_activity_mol_L: float) -> float:
    """Return pH from hydrogen-ion activity for the public reference case."""

    if hydrogen_activity_mol_L <= 0.0 or not isfinite(hydrogen_activity_mol_L):
        raise ValueError("hydrogen_activity_mol_L must be finite and positive")
    return -log10(hydrogen_activity_mol_L)


def charge_balance_residual(
    concentrations_mol_L: Mapping[str, float],
    charges: Mapping[str, int],
) -> float:
    """Return signed charge-balance closure, sum(z_i c_i), in mol/L."""

    if set(concentrations_mol_L) != set(charges):
        raise ValueError("concentrations and charges must describe the same public ions")
    residual = 0.0
    for species_id, concentration in concentrations_mol_L.items():
        value = float(concentration)
        charge = charges[species_id]
        if value < 0.0 or not isfinite(value):
            raise ValueError("charge-balance concentrations must be finite and nonnegative")
        if not isinstance(charge, int):
            raise ValueError("charge numbers must be integers")
        residual += charge * value
    return residual


def fit_beer_lambert_calibration(
    concentrations_mol_L: Sequence[float],
    absorbances: Sequence[float],
    *,
    species_id: str = "unknown",
    path_length_cm: float = 1.0,
    dilution_factor: float = 1.0,
) -> BeerLambertCalibrationResult:
    if path_length_cm <= 0.0 or not isfinite(path_length_cm):
        raise ValueError("path_length_cm must be finite and positive")
    if dilution_factor <= 0.0 or not isfinite(dilution_factor):
        raise ValueError("dilution_factor must be finite and positive")
    if len(concentrations_mol_L) != len(absorbances):
        raise ValueError("concentrations and absorbances must have equal length")
    if len(concentrations_mol_L) < 2:
        raise ValueError("at least two calibration points are required")
    x = np.array([float(value) for value in concentrations_mol_L], dtype=float)
    y = np.array([float(value) for value in absorbances], dtype=float)
    if np.any(~np.isfinite(x)) or np.any(~np.isfinite(y)):
        raise ValueError("calibration points must be finite")
    if np.any(x < 0.0):
        raise ValueError("calibration concentrations must be nonnegative")
    if np.allclose(x, x[0]):
        raise ValueError("calibration concentrations must span a nonzero range")
    design = np.vstack([x, np.ones_like(x)]).T
    slope, intercept = np.linalg.lstsq(design, y, rcond=None)[0]
    if slope <= 0.0:
        raise ValueError("fitted Beer-Lambert slope must be positive")
    fitted = slope * x + intercept
    residuals = y - fitted
    degrees = max(len(x) - 2, 1)
    residual_std = float(np.sqrt(float(np.sum(residuals**2)) / degrees))
    if residual_std <= 1.0e-14:
        residual_std = 0.0
    centered_y = y - float(np.mean(y))
    total_sum_squares = float(np.sum(centered_y**2))
    r_squared = (
        1.0
        if total_sum_squares <= 1.0e-24
        else 1.0 - float(np.sum(residuals**2)) / total_sum_squares
    )
    sxx = float(np.sum((x - float(np.mean(x))) ** 2))
    slope_std_error = 0.0 if sxx <= 0.0 else residual_std / sqrt(sxx)
    detection_limit = 0.0 if residual_std == 0.0 else 3.3 * residual_std / float(slope)
    quantitation_limit = 0.0 if residual_std == 0.0 else 10.0 * residual_std / float(slope)
    return BeerLambertCalibrationResult(
        species_id=species_id,
        path_length_cm=path_length_cm,
        dilution_factor=dilution_factor,
        concentrations_mol_L=tuple(round(float(value), 12) for value in x),
        absorbances=tuple(round(float(value), 12) for value in y),
        fitted_slope_absorbance_per_mol_L=float(slope),
        intercept_absorbance=float(intercept),
        molar_absorptivity_L_mol_cm=float(slope) * dilution_factor / path_length_cm,
        residual_std_absorbance=residual_std,
        slope_std_error=slope_std_error,
        r_squared=float(max(min(r_squared, 1.0), -1.0)),
        detection_limit_mol_L=detection_limit,
        quantitation_limit_mol_L=quantitation_limit,
    )


def generate_beer_lambert_calibration(
    band: BeerLambertBandSpec,
    standard_concentrations_mol_L: Sequence[float],
    *,
    seed: int = 0,
    noise_absorbance: float | None = None,
) -> BeerLambertCalibrationResult:
    noise = band.noise_absorbance if noise_absorbance is None else float(noise_absorbance)
    if noise < 0.0:
        raise ValueError("noise_absorbance cannot be negative")
    rng = np.random.default_rng(seed)
    absorbances = []
    for concentration in standard_concentrations_mol_L:
        absorbance = band.absorbance(float(concentration))
        if noise:
            absorbance += float(rng.normal(0.0, noise))
        absorbances.append(absorbance)
    return fit_beer_lambert_calibration(
        standard_concentrations_mol_L,
        absorbances,
        species_id=band.species_id,
        path_length_cm=band.path_length_cm,
        dilution_factor=band.dilution_factor,
    )


def chromatographic_retention_time(*, dead_time_min: float, retention_factor: float) -> float:
    if dead_time_min <= 0.0 or not isfinite(dead_time_min):
        raise ValueError("dead_time_min must be finite and positive")
    if retention_factor < 0.0 or not isfinite(retention_factor):
        raise ValueError("retention_factor must be finite and nonnegative")
    return dead_time_min * (1.0 + retention_factor)


def chromatographic_retention_factor(
    *,
    retention_time_min: float,
    dead_time_min: float,
) -> float:
    if dead_time_min <= 0.0 or not isfinite(dead_time_min):
        raise ValueError("dead_time_min must be finite and positive")
    if retention_time_min < dead_time_min or not isfinite(retention_time_min):
        raise ValueError("retention_time_min must be finite and at least dead_time_min")
    return (retention_time_min - dead_time_min) / dead_time_min


def chromatographic_baseline_peak_width(
    *,
    retention_time_min: float,
    theoretical_plates: float,
) -> float:
    if retention_time_min <= 0.0 or not isfinite(retention_time_min):
        raise ValueError("retention_time_min must be finite and positive")
    if theoretical_plates <= 0.0 or not isfinite(theoretical_plates):
        raise ValueError("theoretical_plates must be finite and positive")
    return 4.0 * retention_time_min / sqrt(theoretical_plates)


def chromatographic_theoretical_plates(
    *,
    retention_time_min: float,
    baseline_width_min: float,
) -> float:
    if retention_time_min <= 0.0 or not isfinite(retention_time_min):
        raise ValueError("retention_time_min must be finite and positive")
    if baseline_width_min <= 0.0 or not isfinite(baseline_width_min):
        raise ValueError("baseline_width_min must be finite and positive")
    return 16.0 * (retention_time_min / baseline_width_min) ** 2


def chromatographic_resolution(
    retention_time_1_min: float,
    retention_time_2_min: float,
    baseline_width_1_min: float,
    baseline_width_2_min: float,
) -> float:
    if baseline_width_1_min <= 0.0 or baseline_width_2_min <= 0.0:
        raise ValueError("baseline widths must be positive")
    if not all(
        isfinite(value)
        for value in (
            retention_time_1_min,
            retention_time_2_min,
            baseline_width_1_min,
            baseline_width_2_min,
        )
    ):
        raise ValueError("resolution inputs must be finite")
    return 2.0 * abs(retention_time_2_min - retention_time_1_min) / (
        baseline_width_1_min + baseline_width_2_min
    )


def fit_chromatography_calibration(
    retention_times_min: Sequence[float],
    baseline_widths_min: Sequence[float],
    *,
    species_id: str = "unknown",
    instrument_id: str = "hplc",
    dead_time_min: float,
) -> ChromatographyCalibrationResult:
    if instrument_id not in {"hplc", "gc"}:
        raise ValueError("instrument_id must be 'hplc' or 'gc'")
    if dead_time_min <= 0.0 or not isfinite(dead_time_min):
        raise ValueError("dead_time_min must be finite and positive")
    if len(retention_times_min) != len(baseline_widths_min):
        raise ValueError("retention times and baseline widths must have equal length")
    if not retention_times_min:
        raise ValueError("at least one calibration peak is required")
    retention_times = np.array([float(value) for value in retention_times_min], dtype=float)
    widths = np.array([float(value) for value in baseline_widths_min], dtype=float)
    if np.any(~np.isfinite(retention_times)) or np.any(~np.isfinite(widths)):
        raise ValueError("calibration values must be finite")
    if np.any(retention_times < dead_time_min) or np.any(widths <= 0.0):
        raise ValueError("retention times must exceed dead time and widths must be positive")
    retention_factors = np.array(
        [
            chromatographic_retention_factor(
                retention_time_min=float(retention_time),
                dead_time_min=dead_time_min,
            )
            for retention_time in retention_times
        ],
        dtype=float,
    )
    theoretical_plates = np.array(
        [
            chromatographic_theoretical_plates(
                retention_time_min=float(retention_time),
                baseline_width_min=float(width),
            )
            for retention_time, width in zip(retention_times, widths, strict=True)
        ],
        dtype=float,
    )
    return ChromatographyCalibrationResult(
        species_id=species_id,
        instrument_id=instrument_id,
        dead_time_min=dead_time_min,
        retention_times_min=tuple(round(float(value), 12) for value in retention_times),
        baseline_widths_min=tuple(round(float(value), 12) for value in widths),
        retention_factor_mean=float(np.mean(retention_factors)),
        retention_factor_std=float(np.std(retention_factors, ddof=0)),
        retention_time_mean_min=float(np.mean(retention_times)),
        retention_time_std_min=float(np.std(retention_times, ddof=0)),
        theoretical_plates_mean=float(np.mean(theoretical_plates)),
        theoretical_plates_std=float(np.std(theoretical_plates, ddof=0)),
    )


def default_feature_specs(
    instrument_id: str,
    species_ids: Sequence[str],
    *,
    target_species: Sequence[str] = (),
    impurity_species: Sequence[str] = (),
    formulas: Mapping[str, str] | None = None,
) -> tuple[SpectralFeatureSpec, ...]:
    targets = set(target_species)
    impurities = set(impurity_species)
    formula_map = {} if formulas is None else dict(formulas)
    features: list[SpectralFeatureSpec] = []
    for species_id in species_ids:
        role = _species_role(species_id, targets=targets, impurities=impurities)
        features.extend(_features_for_species(instrument_id, species_id, role, formula_map))
    return tuple(features)


def assign_ir_functional_group_bands(
    *,
    species_id: str,
    role: str,
    formula: str,
    strict_formula: bool = True,
) -> IRBandAssignmentReport:
    """Assign compact IR functional-group bands from a formula and benchmark role.

    The rules are intentionally local and auditable. They are not a spectral
    database; they provide chemically interpretable raw-signal features for
    ChemWorld agent tasks.
    """

    if not species_id.strip():
        raise ValueError("species_id cannot be empty")
    normalized_formula = formula.strip()
    warnings: tuple[str, ...]
    if not normalized_formula:
        if strict_formula:
            raise ValueError("formula is required for IR functional-group assignment")
        counts: dict[str, int] = {}
        warnings = ("missing_formula_fingerprint_only",)
    else:
        counts = _formula_element_counts(normalized_formula)
        warnings = () if counts else ("formula_parse_empty_fingerprint_only",)

    carbon = counts.get("C", 0)
    hydrogen = counts.get("H", 0)
    oxygen = counts.get("O", 0)
    nitrogen = counts.get("N", 0)
    sulfur = counts.get("S", 0)
    halogen = sum(counts.get(element, 0) for element in ("F", "Cl", "Br", "I"))

    bands: list[IRFunctionalGroupBandSpec] = [
        _ir_band(
            "fingerprint",
            "fingerprint C-O/C-C/C-N region",
            1130.0,
            70.0,
            0.115,
            species_id=species_id,
            scale=42.0,
        )
    ]
    if carbon and oxygen:
        bands.append(
            _ir_band(
                "carbonyl",
                "C=O stretch",
                1715.0,
                42.0,
                0.235,
                species_id=species_id,
                scale=35.0,
            )
        )
    if oxygen and hydrogen:
        bands.append(
            _ir_band(
                "hydroxyl_broad",
                "O-H broad stretch",
                3340.0,
                190.0,
                0.155,
                species_id=species_id,
                scale=70.0,
                shape="lorentzian",
            )
        )
    if carbon and hydrogen:
        bands.append(
            _ir_band(
                "aliphatic_ch",
                "aliphatic C-H stretch",
                2940.0,
                85.0,
                0.085,
                species_id=species_id,
                scale=45.0,
            )
        )
    if carbon >= 5 and hydrogen >= 4:
        bands.append(
            _ir_band(
                "alkene_aromatic_proxy",
                "C=C/aromatic proxy stretch",
                1605.0,
                55.0,
                0.075,
                species_id=species_id,
                scale=32.0,
            )
        )
    if carbon and nitrogen:
        bands.append(
            _ir_band(
                "nitrile_amine_proxy",
                "C-N/CN proxy stretch",
                2225.0 if hydrogen <= carbon else 1250.0,
                50.0,
                0.070,
                species_id=species_id,
                scale=28.0,
            )
        )
    if sulfur:
        bands.append(
            _ir_band(
                "sulfur_oxygen_proxy",
                "S=O/C-S proxy region",
                1040.0,
                65.0,
                0.080,
                species_id=species_id,
                scale=25.0,
            )
        )
    if halogen:
        bands.append(
            _ir_band(
                "carbon_halogen",
                "C-halogen stretch",
                720.0,
                80.0,
                0.070,
                species_id=species_id,
                scale=45.0,
            )
        )

    interference_pairs = _ir_band_interference_pairs(bands)
    if interference_pairs:
        warnings = (*warnings, "overlapping_ir_bands")
    return IRBandAssignmentReport(
        species_id=species_id,
        role=role,
        formula=normalized_formula,
        element_counts=counts,
        bands=tuple(bands),
        interference_pairs=interference_pairs,
        warnings=warnings,
    )


def synthesize_signal(
    spec: InstrumentSignalSpec,
    amounts_mol: Mapping[str, float],
    *,
    volume_L: float,
    seed: int = 0,
    replicate_count: int = 1,
) -> SpectralMeasurement:
    if volume_L <= 0.0:
        raise ValueError("volume_L must be positive")
    if replicate_count <= 0:
        raise ValueError("replicate_count must be positive")
    concentrations = {
        species_id: max(float(amount), 0.0) / volume_L
        for species_id, amount in amounts_mol.items()
    }
    axis = spec.axis
    peaks = _feature_peaks(spec.features, concentrations)
    overlap_groups = detect_peak_overlap(peaks)
    detected_peaks = _annotate_peaks(peaks, overlap_groups)
    rng = np.random.default_rng(seed)
    replicate_signals: list[tuple[float, ...]] = []
    for _ in range(replicate_count):
        signal = _baseline(axis, spec.baseline, spec.baseline_drift)
        for peak in peaks:
            if bool(peak["detected"]):
                signal += _peak_shape(axis, peak)
        if spec.signal_mode == "transmittance":
            signal = np.clip(1.0 - signal, 0.02, 1.0)
        if spec.noise_std:
            signal = signal + rng.normal(0.0, spec.noise_std, size=signal.shape)
        if spec.signal_mode == "transmittance":
            signal = np.clip(signal, 0.0, 1.0)
        else:
            signal = np.clip(signal, 0.0, None)
            if spec.normalize and float(np.max(signal)) > 0.0:
                signal = signal / float(np.max(signal))
        replicate_signals.append(tuple(_rounded_array(signal)))
    mean_signal = tuple(
        _rounded_array(np.mean(np.array(replicate_signals, dtype=float), axis=0))
    )
    processed, uncertainty = _processed_from_peaks(
        spec.features,
        concentrations,
        detected_peaks,
        replicate_count=replicate_count,
    )
    public_estimate_error_z = {
        species_id: round(float(rng.normal(0.0, 1.0)), 6)
        for species_id in processed
    }
    model_ids = sorted(
        {
            str(feature.metadata["model_id"])
            for feature in spec.features
            if "model_id" in feature.metadata
        }
    )
    calibration_profile = (
        "uvvis_beer_lambert_calibration_v1"
        if spec.instrument_id == "uvvis"
        else "ir_functional_group_calibration_v1"
        if spec.instrument_id == "ir"
        else f"{spec.instrument_id}_retention_plate_calibration_v1"
        if spec.instrument_id in {"hplc", "gc"}
        else f"{spec.instrument_id}_species_calibration_v1"
    )
    chromatographic_resolution_summary = _chromatographic_resolution_summary(detected_peaks)
    metadata: dict[str, object] = {
        "axis_unit": spec.axis_unit,
        "baseline": spec.baseline,
        "baseline_drift": spec.baseline_drift,
        "calibration_profile": calibration_profile,
        "detection_limits_mol_L": {
            feature.species_id: feature.detection_limit_mol_L
            for feature in spec.features
        },
        "peak_overlap": any(bool(peak["overlap_group"]) for peak in detected_peaks),
        "model_ids": model_ids,
        "detector_gain": spec.detector_gain,
        "public_estimate_error_z": public_estimate_error_z,
    }
    if chromatographic_resolution_summary:
        metadata["chromatographic_resolution"] = chromatographic_resolution_summary
    if spec.instrument_id == "ir":
        functional_groups: set[str] = set()
        for peak in detected_peaks:
            peak_metadata = peak.get("metadata")
            if (
                isinstance(peak_metadata, Mapping)
                and peak_metadata.get("model_id") == "ir_functional_group_bands"
            ):
                functional_groups.add(str(peak_metadata.get("group_id")))
        metadata["ir_functional_groups"] = sorted(functional_groups)
        metadata["ir_interference"] = _ir_interference_summary(detected_peaks)
    return SpectralMeasurement(
        instrument_id=spec.instrument_id,
        kind=spec.kind,
        axis_key=spec.axis_key,
        signal_key=spec.signal_key,
        axis=tuple(_rounded_array(axis)),
        signal=mean_signal,
        replicate_signals=tuple(replicate_signals),
        peaks=tuple(detected_peaks),
        processed_estimates=processed,
        uncertainty=uncertainty,
        metadata=metadata,
    )


def synthesize_signal_from_card(
    instrument_id: str,
    card: MechanismScenarioCard,
    network: ReactionNetworkSpec,
    amounts_mol: Mapping[str, float],
    *,
    volume_L: float,
    seed: int = 0,
    replicate_count: int = 1,
) -> SpectralMeasurement:
    spec = build_signal_spec_from_card(instrument_id, card, network)
    return synthesize_signal(
        spec,
        amounts_mol,
        volume_L=volume_L,
        seed=seed,
        replicate_count=replicate_count,
    )


def detect_peak_overlap(peaks: Sequence[Mapping[str, object]]) -> dict[int, int]:
    groups: dict[int, int] = {}
    next_group = 1
    for idx, peak in enumerate(peaks):
        if not bool(peak["detected"]):
            continue
        center = _as_float(peak["center"])
        width = _as_float(peak["width"])
        for other_idx, other in enumerate(peaks[:idx]):
            if not bool(other["detected"]):
                continue
            distance = abs(center - _as_float(other["center"]))
            limit = 0.85 * (width + _as_float(other["width"]))
            if distance <= limit:
                group = groups.get(other_idx, next_group)
                groups[other_idx] = group
                groups[idx] = group
                if group == next_group:
                    next_group += 1
                break
    return groups


def _features_for_species(
    instrument_id: str,
    species_id: str,
    role: str,
    formulas: Mapping[str, str],
) -> tuple[SpectralFeatureSpec, ...]:
    if instrument_id == "hplc":
        return (_chromatography_feature(instrument_id, species_id, role),)
    if instrument_id == "gc":
        if not _gc_visible(species_id, role):
            return ()
        return (_chromatography_feature(instrument_id, species_id, role),)
    if instrument_id == "uvvis":
        return (_uvvis_feature(species_id, role),)
    if instrument_id == "ir":
        return _ir_features(species_id, role, formulas.get(species_id, ""))
    if instrument_id == "nmr":
        return _nmr_features(species_id, role)
    raise ValueError(f"Unsupported instrument_id={instrument_id!r}")


def _chromatography_feature(
    instrument_id: str,
    species_id: str,
    role: str,
) -> SpectralFeatureSpec:
    if instrument_id == "hplc":
        method = ChromatographyMethodSpec(
            instrument_id="hplc",
            dead_time_min=0.62,
            theoretical_plates=7200.0,
            retention_factor_by_group={
                "reactant": 0.86,
                "target": 3.22,
                "byproduct": 4.25,
                "degradation": 5.45,
                "catalyst": 7.40,
                "other": 2.45,
            },
            response_factor_by_group={
                "target": 950.0,
                "reactant": 620.0,
                "byproduct": 640.0,
                "degradation": 590.0,
                "catalyst": 420.0,
                "other": 560.0,
            },
            detection_limit_mol_L=0.0008,
            noise_relative=0.025,
        )
    else:
        method = ChromatographyMethodSpec(
            instrument_id="gc",
            dead_time_min=0.34,
            theoretical_plates=5400.0,
            retention_factor_by_group={
                "reactant": 1.35,
                "target": 5.90,
                "byproduct": 2.10,
                "degradation": 3.85,
                "catalyst": 8.70,
                "other": 3.25,
            },
            response_factor_by_group={
                "target": 760.0,
                "reactant": 540.0,
                "byproduct": 600.0,
                "degradation": 570.0,
                "catalyst": 390.0,
                "other": 520.0,
            },
            detection_limit_mol_L=0.0012,
            noise_relative=0.030,
        )
    metadata = method.feature_metadata(species_id=species_id, group=role)
    center = _as_float(metadata["retention_time_min"])
    width = _as_float(metadata["gaussian_sigma_min"])
    response = method.response_factor(role)
    detection = method.detection_limit_mol_L
    return SpectralFeatureSpec(
        species_id=species_id,
        instrument_id=instrument_id,
        center=center,
        width=width,
        response_factor=response,
        detection_limit_mol_L=detection,
        assignment=f"{species_id}_{role}",
        group=role,
        calibration=CalibrationCurve(
            slope=response,
            lower_limit=detection,
            upper_limit=5.0,
            noise_relative=method.noise_relative,
        ),
        metadata=metadata,
    )


def _uvvis_feature(species_id: str, role: str) -> SpectralFeatureSpec:
    centers = {
        "reactant": 365.0,
        "target": 430.0,
        "byproduct": 515.0,
        "degradation": 560.0,
        "catalyst": 680.0,
        "other": 470.0,
    }
    absorptivities = {
        "reactant": 420.0,
        "target": 950.0,
        "byproduct": 560.0,
        "degradation": 720.0,
        "catalyst": 240.0,
        "other": 360.0,
    }
    center = centers.get(role, centers["other"]) + _stable_offset(species_id, scale=18.0)
    band = BeerLambertBandSpec(
        species_id=species_id,
        wavelength_nm=center,
        molar_absorptivity_L_mol_cm=absorptivities.get(role, absorptivities["other"]),
        path_length_cm=1.0,
        dilution_factor=1000.0,
        bandwidth_nm=34.0 if role != "catalyst" else 48.0,
        blank_absorbance=0.020,
        detection_limit_mol_L=0.0025,
        noise_absorbance=0.0015,
        assignment=f"{species_id}_{role}_beer_lambert_band",
        group=role,
    )
    return SpectralFeatureSpec(
        species_id=species_id,
        instrument_id="uvvis",
        center=center,
        width=band.bandwidth_nm,
        response_factor=1.0,
        detection_limit_mol_L=0.0025,
        assignment=band.assignment,
        group=role,
        calibration=band.calibration_curve(),
        metadata=band.to_dict(),
    )


def _ir_features(species_id: str, role: str, formula: str) -> tuple[SpectralFeatureSpec, ...]:
    report = assign_ir_functional_group_bands(
        species_id=species_id,
        role=role,
        formula=formula,
        strict_formula=False,
    )
    warning = ";".join(report.warnings) if report.warnings else None
    return tuple(
        band.to_feature(
            species_id=species_id,
            role=role,
            formula=report.formula,
            warning=warning,
        )
        for band in report.bands
    )


def _nmr_features(species_id: str, role: str) -> tuple[SpectralFeatureSpec, ...]:
    centers = {
        "reactant": (2.05, 4.20),
        "target": (1.28, 3.72),
        "byproduct": (2.40, 6.85),
        "degradation": (2.20, 9.55),
        "catalyst": (0.65,),
        "other": (3.20,),
    }
    response = 0.35 if role == "target" else 0.24
    return tuple(
        SpectralFeatureSpec(
            species_id=species_id,
            instrument_id="nmr",
            center=center + _stable_offset(f"{species_id}{idx}", scale=0.08),
            width=0.045 if center < 5.0 else 0.070,
            response_factor=response,
            detection_limit_mol_L=0.003,
            assignment=f"{species_id}_{role}_nmr_{idx}",
            group=role,
            calibration=CalibrationCurve(
                slope=response,
                lower_limit=0.003,
                upper_limit=5.0,
                noise_relative=0.04,
            ),
        )
        for idx, center in enumerate(centers.get(role, centers["other"]))
    )


def _species_role(species_id: str, *, targets: set[str], impurities: set[str]) -> str:
    lowered = species_id.lower()
    if species_id in targets:
        return "target"
    if species_id in impurities:
        if "degrad" in lowered:
            return "degradation"
        return "byproduct"
    if "reactant" in lowered:
        return "reactant"
    if "catalyst" in lowered:
        return "catalyst"
    if "target" in lowered or "product" in lowered:
        return "target"
    if "byproduct" in lowered or "impurity" in lowered:
        return "byproduct"
    return "other"


def _gc_visible(species_id: str, role: str) -> bool:
    lowered = species_id.lower()
    if "vapor" in lowered or "volatile" in lowered:
        return True
    if any(token in lowered for token in ("alcohol", "water", "ether", "solvent")):
        return True
    return role in {"byproduct", "degradation", "target"}


def _feature_peaks(
    features: Sequence[SpectralFeatureSpec],
    concentrations_mol_L: Mapping[str, float],
) -> list[dict[str, object]]:
    peaks: list[dict[str, object]] = []
    for feature in features:
        concentration = max(float(concentrations_mol_L.get(feature.species_id, 0.0)), 0.0)
        detected = concentration >= feature.detection_limit_mol_L
        raw_area = feature.calibration.response(concentration) * feature.response_factor
        area = raw_area if detected else 0.0
        peaks.append(
            {
                "species_id": feature.species_id,
                "assignment": feature.assignment,
                "group": feature.group,
                "center": feature.center,
                "width": feature.width,
                "area": area,
                "detected": detected,
                "detection_limit_mol_L": feature.detection_limit_mol_L,
                "response_factor": feature.response_factor,
                "shape": feature.shape,
                "calibration": feature.calibration,
                "feature_metadata": dict(feature.metadata),
            }
        )
    return peaks


def _annotate_peaks(
    peaks: Sequence[Mapping[str, object]],
    overlap_groups: Mapping[int, int],
) -> list[dict[str, object]]:
    annotated: list[dict[str, object]] = []
    for idx, peak in enumerate(peaks):
        calibration = peak["calibration"]
        if not isinstance(calibration, CalibrationCurve):
            raise TypeError("Internal peak calibration must be a CalibrationCurve")
        area = _as_float(peak["area"])
        response = area / max(_as_float(peak["response_factor"]), 1.0e-12)
        estimated = calibration.estimate_concentration(response)
        feature_metadata = peak.get("feature_metadata", {})
        if not isinstance(feature_metadata, Mapping):
            feature_metadata = {}
        annotated.append(
            {
                "species_id": str(peak["species_id"]),
                "assignment": str(peak["assignment"]),
                "group": str(peak["group"]),
                "center": round(_as_float(peak["center"]), 6),
                "width": round(_as_float(peak["width"]), 6),
                "area": round(area, 6),
                "detected": bool(peak["detected"]),
                "detection_limit_mol_L": round(
                    _as_float(peak["detection_limit_mol_L"]),
                    9,
                ),
                "estimated_concentration_mol_L": round(estimated, 9),
                "overlap_group": overlap_groups.get(idx),
                "metadata": dict(feature_metadata),
            }
        )
    return annotated


def _chromatographic_resolution_summary(
    peaks: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    chromatographic: list[Mapping[str, object]] = []
    for peak in peaks:
        metadata = peak.get("metadata", {})
        if (
            bool(peak["detected"])
            and isinstance(metadata, Mapping)
            and metadata.get("model_id") == "chromatography_retention_plate"
        ):
            chromatographic.append(peak)
    if len(chromatographic) < 2:
        return {}
    ordered = sorted(chromatographic, key=lambda peak: _as_float(peak["center"]))
    resolutions: list[tuple[float, str, str]] = []
    for left, right in pairwise(ordered):
        left_metadata = left["metadata"]
        right_metadata = right["metadata"]
        if not isinstance(left_metadata, Mapping) or not isinstance(right_metadata, Mapping):
            continue
        resolution = chromatographic_resolution(
            _as_float(left["center"]),
            _as_float(right["center"]),
            _as_float(left_metadata["baseline_width_min"]),
            _as_float(right_metadata["baseline_width_min"]),
        )
        resolutions.append(
            (
                resolution,
                str(left["species_id"]),
                str(right["species_id"]),
            )
        )
    if not resolutions:
        return {}
    minimum_resolution, left_species, right_species = min(
        resolutions,
        key=lambda item: item[0],
    )
    return {
        "minimum_adjacent_resolution": round(minimum_resolution, 6),
        "critical_pair": [left_species, right_species],
        "well_resolved": minimum_resolution >= 1.5,
    }


def _ir_interference_summary(peaks: Sequence[Mapping[str, object]]) -> dict[str, object]:
    ir_peaks: list[Mapping[str, object]] = []
    for peak in peaks:
        peak_metadata = peak.get("metadata")
        if (
            isinstance(peak_metadata, Mapping)
            and peak_metadata.get("model_id") == "ir_functional_group_bands"
        ):
            ir_peaks.append(peak)
    pairs: list[dict[str, object]] = []
    for left, right in pairwise(sorted(ir_peaks, key=lambda peak: _as_float(peak["center"]))):
        distance = abs(_as_float(right["center"]) - _as_float(left["center"]))
        limit = 0.55 * (_as_float(left["width"]) + _as_float(right["width"]))
        if distance <= limit:
            pairs.append(
                {
                    "left_assignment": str(left["assignment"]),
                    "right_assignment": str(right["assignment"]),
                    "center_distance_cm_inv": round(distance, 6),
                    "resolution_proxy": round(distance / max(limit, 1.0e-12), 6),
                }
            )
    return {
        "overlap_pairs": pairs,
        "unresolved": bool(pairs),
    }


def _processed_from_peaks(
    features: Sequence[SpectralFeatureSpec],
    concentrations: Mapping[str, float],
    peaks: Sequence[Mapping[str, object]],
    *,
    replicate_count: int,
) -> tuple[dict[str, float], dict[str, float]]:
    by_species_feature = {(feature.species_id, feature.assignment): feature for feature in features}
    estimates: dict[str, list[float]] = {}
    uncertainties: dict[str, list[float]] = {}
    for peak in peaks:
        if not bool(peak["detected"]):
            continue
        species_id = str(peak["species_id"])
        assignment = str(peak["assignment"])
        feature = by_species_feature[(species_id, assignment)]
        concentration = concentrations.get(species_id, 0.0)
        relative = feature.calibration.noise_relative / sqrt(float(replicate_count))
        estimates.setdefault(species_id, []).append(float(concentration))
        uncertainties.setdefault(species_id, []).append(max(concentration * relative, 1.0e-9))
    processed = {
        species_id: round(float(np.mean(values)), 9)
        for species_id, values in sorted(estimates.items())
    }
    uncertainty = {
        f"{species_id}_std_mol_L": round(float(np.mean(values)), 9)
        for species_id, values in sorted(uncertainties.items())
    }
    return processed, uncertainty


def _baseline(axis: np.ndarray, intercept: float, drift: float) -> np.ndarray:
    span = max(float(axis[-1] - axis[0]), 1.0)
    normalized = (axis - axis[0]) / span
    return intercept + drift * normalized


def _peak_shape(axis: np.ndarray, peak: Mapping[str, object]) -> np.ndarray:
    center = _as_float(peak["center"])
    width = max(_as_float(peak["width"]), 1.0e-9)
    area = _as_float(peak["area"])
    if str(peak["shape"]) == "lorentzian":
        gamma = width / 2.0
        return area * (gamma / np.pi) / ((axis - center) ** 2 + gamma**2)
    height = area / (width * np.sqrt(2.0 * np.pi))
    return height * np.exp(-0.5 * ((axis - center) / width) ** 2)


def _ir_band(
    group_id: str,
    assignment: str,
    center_cm_inv: float,
    width_cm_inv: float,
    relative_intensity: float,
    *,
    species_id: str,
    scale: float,
    shape: PeakShape = "gaussian",
) -> IRFunctionalGroupBandSpec:
    return IRFunctionalGroupBandSpec(
        group_id=group_id,
        assignment=assignment,
        center_cm_inv=center_cm_inv + _stable_offset(f"{species_id}:{group_id}", scale=scale),
        width_cm_inv=width_cm_inv,
        relative_intensity=relative_intensity,
        shape=shape,
    )


def _ir_band_interference_pairs(
    bands: Sequence[IRFunctionalGroupBandSpec],
) -> tuple[tuple[str, str], ...]:
    pairs: list[tuple[str, str]] = []
    for left, right in pairwise(sorted(bands, key=lambda band: band.center_cm_inv)):
        distance = abs(right.center_cm_inv - left.center_cm_inv)
        limit = 0.55 * (left.width_cm_inv + right.width_cm_inv)
        if distance <= limit:
            pairs.append((left.group_id, right.group_id))
    return tuple(pairs)


def _formula_element_counts(formula: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for element, count_text in re.findall(r"([A-Z][a-z]?)(\d*)", formula):
        counts[element] = counts.get(element, 0) + int(count_text or "1")
    return counts


def _stable_offset(text: str, *, scale: float) -> float:
    bucket = sum((idx + 1) * ord(char) for idx, char in enumerate(text)) % 101
    return ((bucket / 100.0) - 0.5) * scale


def _rounded_array(values: np.ndarray, digits: int = 6) -> list[float]:
    return [round(float(value), digits) for value in values]


def _as_float(value: object) -> float:
    if isinstance(value, int | float | str):
        return float(value)
    raise TypeError(f"Expected a numeric value, got {type(value).__name__}")


def _public_calibration_method(instrument_id: str) -> str:
    return {
        "uvvis": "Beer-Lambert linear calibration",
        "hplc": "retention-factor and plate-count calibration",
        "gc": "retention-factor and plate-count calibration",
        "ir": "synthetic functional-region response calibration",
        "nmr": "synthetic chemical-shift response calibration",
    }.get(instrument_id, "synthetic linear calibration")


def _signal_unit(instrument_id: str) -> str:
    return {
        "uvvis": "absorbance",
        "ir": "transmittance_fraction",
        "hplc": "relative_detector_response",
        "gc": "relative_detector_response",
        "nmr": "relative_intensity",
    }.get(instrument_id, "a.u.")


def _public_assignment_label(group: str) -> str:
    return {
        "reactant": "reactant_proxy",
        "target": "target_product_proxy",
        "byproduct": "byproduct_proxy",
        "degradation": "degradation_proxy",
        "catalyst": "catalyst_proxy",
    }.get(group, "unassigned_proxy")


__all__ = [
    "BeerLambertBandSpec",
    "BeerLambertCalibrationResult",
    "CalibrationCurve",
    "ChromatographyCalibrationResult",
    "ChromatographyMethodSpec",
    "IRBandAssignmentReport",
    "IRFunctionalGroupBandSpec",
    "InstrumentSignalSpec",
    "SpectralFeatureSpec",
    "SpectralMeasurement",
    "assign_ir_functional_group_bands",
    "beer_lambert_absorbance",
    "build_signal_spec",
    "build_signal_spec_from_card",
    "charge_balance_residual",
    "chromatographic_baseline_peak_width",
    "chromatographic_resolution",
    "chromatographic_retention_factor",
    "chromatographic_retention_time",
    "chromatographic_theoretical_plates",
    "default_feature_specs",
    "detect_peak_overlap",
    "fit_beer_lambert_calibration",
    "fit_chromatography_calibration",
    "generate_beer_lambert_calibration",
    "potentiometric_ph",
    "spectroscopy_model_cards",
    "synthesize_signal",
    "synthesize_signal_from_card",
]
