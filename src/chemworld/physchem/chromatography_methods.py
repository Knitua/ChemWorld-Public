"""Empirical HPLC/GC method sensitivity and detector calibration."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from math import exp, isfinite, log, log10, sqrt
from typing import Literal

import numpy as np

R_J_PER_MOL_K = 8.31446261815324
ChromatographyInstrument = Literal["hplc", "gc"]


@dataclass(frozen=True)
class EmpiricalChromatographyAnalyteSpec:
    analyte_id: str
    instrument_id: ChromatographyInstrument
    reference_retention_factor: float
    reference_temperature_K: float
    reference_mobile_phase_fraction: float | None
    hplc_log10_k_mobile_phase_slope: float = 0.0
    hplc_log10_k_temperature_slope_per_K: float = 0.0
    gc_retention_enthalpy_J_mol: float = 0.0
    detector_response_slope: float = 1.0
    detector_response_intercept: float = 0.0
    tailing_factor: float = 1.0
    theoretical_plates: float = 5000.0
    provenance_id: str = ""

    def __post_init__(self) -> None:
        if not self.analyte_id or not self.provenance_id:
            raise ValueError("analyte_id and provenance_id cannot be empty")
        if self.instrument_id not in {"hplc", "gc"}:
            raise ValueError("instrument_id must be hplc or gc")
        _positive(self.reference_retention_factor, "reference_retention_factor")
        _positive(self.reference_temperature_K, "reference_temperature_K")
        _positive(self.detector_response_slope, "detector_response_slope")
        _positive(self.tailing_factor, "tailing_factor")
        _positive(self.theoretical_plates, "theoretical_plates")
        for name, value in (
            (
                "hplc_log10_k_mobile_phase_slope",
                self.hplc_log10_k_mobile_phase_slope,
            ),
            (
                "hplc_log10_k_temperature_slope_per_K",
                self.hplc_log10_k_temperature_slope_per_K,
            ),
            ("gc_retention_enthalpy_J_mol", self.gc_retention_enthalpy_J_mol),
            ("detector_response_intercept", self.detector_response_intercept),
        ):
            _finite(value, name)
        if self.instrument_id == "hplc":
            if self.reference_mobile_phase_fraction is None or not (
                0.0 <= self.reference_mobile_phase_fraction <= 1.0
            ):
                raise ValueError("HPLC analytes require reference_mobile_phase_fraction in [0, 1]")
        elif self.reference_mobile_phase_fraction is not None:
            raise ValueError("GC analytes do not use reference_mobile_phase_fraction")

    def to_dict(self) -> dict[str, object]:
        return {
            "analyte_id": self.analyte_id,
            "instrument_id": self.instrument_id,
            "reference_retention_factor": self.reference_retention_factor,
            "reference_temperature_K": self.reference_temperature_K,
            "reference_mobile_phase_fraction": self.reference_mobile_phase_fraction,
            "hplc_log10_k_mobile_phase_slope": (self.hplc_log10_k_mobile_phase_slope),
            "hplc_log10_k_temperature_slope_per_K": (self.hplc_log10_k_temperature_slope_per_K),
            "gc_retention_enthalpy_J_mol": self.gc_retention_enthalpy_J_mol,
            "detector_response_slope": self.detector_response_slope,
            "detector_response_intercept": self.detector_response_intercept,
            "tailing_factor": self.tailing_factor,
            "theoretical_plates": self.theoretical_plates,
            "provenance_id": self.provenance_id,
        }


@dataclass(frozen=True)
class ChromatographyMethodReport:
    model_id: str
    analyte_id: str
    instrument_id: ChromatographyInstrument
    dead_time_min: float
    temperature_K: float
    mobile_phase_fraction: float | None
    retention_factor: float
    retention_time_min: float
    retention_shift_min: float
    theoretical_plates: float
    baseline_peak_width_min: float
    detector_concentration: float
    detector_response: float
    tailing_factor: float
    peak_shape_status: str
    asymmetric_peak: bool
    warnings: tuple[str, ...]
    provenance_id: str

    def to_dict(self) -> dict[str, object]:
        return {
            "model_id": self.model_id,
            "analyte_id": self.analyte_id,
            "instrument_id": self.instrument_id,
            "dead_time_min": self.dead_time_min,
            "temperature_K": self.temperature_K,
            "mobile_phase_fraction": self.mobile_phase_fraction,
            "retention_factor": self.retention_factor,
            "retention_time_min": self.retention_time_min,
            "retention_shift_min": self.retention_shift_min,
            "theoretical_plates": self.theoretical_plates,
            "baseline_peak_width_min": self.baseline_peak_width_min,
            "detector_concentration": self.detector_concentration,
            "detector_response": self.detector_response,
            "tailing_factor": self.tailing_factor,
            "peak_shape_status": self.peak_shape_status,
            "asymmetric_peak": self.asymmetric_peak,
            "warnings": list(self.warnings),
            "provenance_id": self.provenance_id,
        }


@dataclass(frozen=True)
class DetectorResponseCalibrationResult:
    detector_id: str
    concentrations: tuple[float, ...]
    responses: tuple[float, ...]
    slope: float
    intercept: float
    slope_standard_error: float
    residual_standard_deviation: float
    r_squared: float
    detection_limit: float
    quantitation_limit: float
    provenance_id: str

    def response(self, concentration: float) -> float:
        _nonnegative(concentration, "concentration")
        return self.intercept + self.slope * concentration

    def concentration(self, response: float) -> float:
        _finite(response, "response")
        return max((response - self.intercept) / self.slope, 0.0)

    def to_dict(self) -> dict[str, object]:
        return {
            "detector_id": self.detector_id,
            "concentrations": list(self.concentrations),
            "responses": list(self.responses),
            "slope": self.slope,
            "intercept": self.intercept,
            "slope_standard_error": self.slope_standard_error,
            "residual_standard_deviation": self.residual_standard_deviation,
            "r_squared": self.r_squared,
            "detection_limit": self.detection_limit,
            "quantitation_limit": self.quantitation_limit,
            "provenance_id": self.provenance_id,
        }


def evaluate_chromatography_method(
    analyte: EmpiricalChromatographyAnalyteSpec,
    *,
    dead_time_min: float,
    temperature_K: float,
    detector_concentration: float,
    mobile_phase_fraction: float | None = None,
) -> ChromatographyMethodReport:
    _positive(dead_time_min, "dead_time_min")
    _positive(temperature_K, "temperature_K")
    _nonnegative(detector_concentration, "detector_concentration")
    reference_time = dead_time_min * (1.0 + analyte.reference_retention_factor)
    if analyte.instrument_id == "hplc":
        if mobile_phase_fraction is None or not 0.0 <= mobile_phase_fraction <= 1.0:
            raise ValueError("HPLC evaluation requires mobile_phase_fraction in [0, 1]")
        reference_fraction = analyte.reference_mobile_phase_fraction
        if reference_fraction is None:  # pragma: no cover - guarded by spec validation
            raise RuntimeError("HPLC reference mobile-phase fraction is missing")
        log10_k = log10(analyte.reference_retention_factor)
        log10_k -= analyte.hplc_log10_k_mobile_phase_slope * (
            mobile_phase_fraction - reference_fraction
        )
        log10_k += analyte.hplc_log10_k_temperature_slope_per_K * (
            temperature_K - analyte.reference_temperature_K
        )
        retention_factor = 10.0**log10_k
    else:
        if mobile_phase_fraction is not None:
            raise ValueError("GC evaluation does not accept mobile_phase_fraction")
        retention_factor = analyte.reference_retention_factor * exp(
            -analyte.gc_retention_enthalpy_J_mol
            / R_J_PER_MOL_K
            * (1.0 / temperature_K - 1.0 / analyte.reference_temperature_K)
        )
    retention_time = dead_time_min * (1.0 + retention_factor)
    baseline_peak_width = 4.0 * retention_time / sqrt(analyte.theoretical_plates)
    response = (
        analyte.detector_response_intercept
        + analyte.detector_response_slope * detector_concentration
    )
    shape_status = peak_shape_status(analyte.tailing_factor)
    warnings: list[str] = []
    if shape_status != "symmetric":
        warnings.append(f"asymmetric_peak_{shape_status}")
    if retention_factor < 0.2:
        warnings.append("weak_retention_near_dead_time")
    if retention_factor > 20.0:
        warnings.append("strong_retention_long_runtime")
    return ChromatographyMethodReport(
        model_id="empirical_chromatography_method_sensitivity_v1",
        analyte_id=analyte.analyte_id,
        instrument_id=analyte.instrument_id,
        dead_time_min=dead_time_min,
        temperature_K=temperature_K,
        mobile_phase_fraction=mobile_phase_fraction,
        retention_factor=retention_factor,
        retention_time_min=retention_time,
        retention_shift_min=retention_time - reference_time,
        theoretical_plates=analyte.theoretical_plates,
        baseline_peak_width_min=baseline_peak_width,
        detector_concentration=detector_concentration,
        detector_response=response,
        tailing_factor=analyte.tailing_factor,
        peak_shape_status=shape_status,
        asymmetric_peak=shape_status != "symmetric",
        warnings=tuple(warnings),
        provenance_id=analyte.provenance_id,
    )


def gc_linear_retention_index(
    *,
    unknown_retention_time_min: float,
    dead_time_min: float,
    lower_alkane_carbon_number: int,
    lower_alkane_retention_time_min: float,
    upper_alkane_carbon_number: int,
    upper_alkane_retention_time_min: float,
) -> float:
    """Interpolate a logarithmic GC retention index between n-alkanes."""

    _positive(dead_time_min, "dead_time_min")
    if lower_alkane_carbon_number <= 0 or upper_alkane_carbon_number <= 0:
        raise ValueError("alkane carbon numbers must be positive")
    if upper_alkane_carbon_number <= lower_alkane_carbon_number:
        raise ValueError("upper alkane carbon number must exceed lower")
    adjusted_unknown = unknown_retention_time_min - dead_time_min
    adjusted_lower = lower_alkane_retention_time_min - dead_time_min
    adjusted_upper = upper_alkane_retention_time_min - dead_time_min
    if not 0.0 < adjusted_lower < adjusted_unknown < adjusted_upper:
        raise ValueError("unknown adjusted retention must be bracketed by alkane anchors")
    fraction = (log(adjusted_unknown) - log(adjusted_lower)) / (
        log(adjusted_upper) - log(adjusted_lower)
    )
    return 100.0 * (
        lower_alkane_carbon_number
        + (upper_alkane_carbon_number - lower_alkane_carbon_number) * fraction
    )


def fit_detector_response_calibration(
    concentrations: Sequence[float],
    responses: Sequence[float],
    *,
    detector_id: str,
    provenance_id: str,
) -> DetectorResponseCalibrationResult:
    if not detector_id or not provenance_id:
        raise ValueError("detector_id and provenance_id cannot be empty")
    if len(concentrations) != len(responses) or len(concentrations) < 3:
        raise ValueError("detector calibration requires at least three paired points")
    x = np.asarray(concentrations, dtype=float)
    y = np.asarray(responses, dtype=float)
    if np.any(~np.isfinite(x)) or np.any(~np.isfinite(y)) or np.any(x < 0.0):
        raise ValueError("calibration data must be finite with nonnegative concentration")
    if np.allclose(x, x[0]):
        raise ValueError("calibration concentrations must span a nonzero range")
    design = np.vstack((x, np.ones_like(x))).T
    slope, intercept = np.linalg.lstsq(design, y, rcond=None)[0]
    if slope <= 0.0:
        raise ValueError("detector calibration slope must be positive")
    residuals = y - (slope * x + intercept)
    degrees = max(len(x) - 2, 1)
    residual_std = sqrt(float(np.sum(residuals**2)) / degrees)
    centered = y - float(np.mean(y))
    total = float(np.sum(centered**2))
    r_squared = 1.0 if total <= 1.0e-24 else 1.0 - float(np.sum(residuals**2)) / total
    sxx = float(np.sum((x - float(np.mean(x))) ** 2))
    slope_error = 0.0 if sxx <= 0.0 else residual_std / sqrt(sxx)
    return DetectorResponseCalibrationResult(
        detector_id=detector_id,
        concentrations=tuple(float(value) for value in x),
        responses=tuple(float(value) for value in y),
        slope=float(slope),
        intercept=float(intercept),
        slope_standard_error=slope_error,
        residual_standard_deviation=residual_std,
        r_squared=max(min(r_squared, 1.0), -1.0),
        detection_limit=3.3 * residual_std / float(slope),
        quantitation_limit=10.0 * residual_std / float(slope),
        provenance_id=provenance_id,
    )


def peak_shape_status(tailing_factor: float) -> str:
    _positive(tailing_factor, "tailing_factor")
    if tailing_factor < 0.5:
        return "severe_fronting"
    if tailing_factor < 0.8:
        return "fronting"
    if tailing_factor <= 1.2:
        return "symmetric"
    if tailing_factor <= 2.0:
        return "tailing"
    return "severe_tailing"


def _positive(value: float, field_name: str) -> None:
    if value <= 0.0 or not isfinite(value):
        raise ValueError(f"{field_name} must be positive and finite")


def _nonnegative(value: float, field_name: str) -> None:
    if value < 0.0 or not isfinite(value):
        raise ValueError(f"{field_name} must be nonnegative and finite")


def _finite(value: float, field_name: str) -> None:
    if not isfinite(value):
        raise ValueError(f"{field_name} must be finite")


__all__ = [
    "ChromatographyMethodReport",
    "DetectorResponseCalibrationResult",
    "EmpiricalChromatographyAnalyteSpec",
    "evaluate_chromatography_method",
    "fit_detector_response_calibration",
    "gc_linear_retention_index",
    "peak_shape_status",
]
