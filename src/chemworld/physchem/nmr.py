"""First-order proton NMR assignments, splitting, and integration reports."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from math import isfinite
from typing import Literal

NMRMultiplicity = Literal["s", "br_s", "d", "t", "q", "quint", "dd", "m"]


@dataclass(frozen=True)
class ProtonNMRSignalSpec:
    species_id: str
    signal_id: str
    chemical_shift_ppm: float
    proton_count: int
    multiplicity: NMRMultiplicity
    coupling_constants_Hz: tuple[float, ...]
    line_width_Hz: float
    assignment: str
    provenance_id: str
    exchangeable: bool = False
    response_factor: float = 1.0

    def __post_init__(self) -> None:
        if not all((self.species_id, self.signal_id, self.assignment, self.provenance_id)):
            raise ValueError("NMR signal ids, assignment, and provenance cannot be empty")
        if self.chemical_shift_ppm < 0.0 or not isfinite(self.chemical_shift_ppm):
            raise ValueError("chemical_shift_ppm must be finite and nonnegative")
        if self.proton_count <= 0:
            raise ValueError("proton_count must be positive")
        if self.multiplicity not in {"s", "br_s", "d", "t", "q", "quint", "dd", "m"}:
            raise ValueError("unsupported NMR multiplicity")
        if any(value <= 0.0 or not isfinite(value) for value in self.coupling_constants_Hz):
            raise ValueError("coupling constants must be positive and finite")
        expected_couplings = {
            "s": 0,
            "br_s": 0,
            "d": 1,
            "t": 1,
            "q": 1,
            "quint": 1,
            "dd": 2,
        }
        if (
            self.multiplicity in expected_couplings
            and len(self.coupling_constants_Hz) != expected_couplings[self.multiplicity]
        ):
            raise ValueError("coupling count does not match declared multiplicity")
        _positive(self.line_width_Hz, "line_width_Hz")
        _positive(self.response_factor, "response_factor")

    def to_dict(self) -> dict[str, object]:
        return {
            "species_id": self.species_id,
            "signal_id": self.signal_id,
            "chemical_shift_ppm": self.chemical_shift_ppm,
            "proton_count": self.proton_count,
            "multiplicity": self.multiplicity,
            "coupling_constants_Hz": list(self.coupling_constants_Hz),
            "line_width_Hz": self.line_width_Hz,
            "assignment": self.assignment,
            "provenance_id": self.provenance_id,
            "exchangeable": self.exchangeable,
            "response_factor": self.response_factor,
        }


@dataclass(frozen=True)
class ProtonNMRMethodSpec:
    method_id: str
    spectrometer_frequency_MHz: float
    solvent_id: str
    solvent_residual_peaks_ppm: tuple[float, ...]
    reference_id: str
    expected_reference_ppm: float
    observed_reference_ppm: float
    solvent_interference_tolerance_ppm: float = 0.03

    def __post_init__(self) -> None:
        if not self.method_id or not self.solvent_id or not self.reference_id:
            raise ValueError("NMR method, solvent, and reference ids cannot be empty")
        _positive(self.spectrometer_frequency_MHz, "spectrometer_frequency_MHz")
        for name, value in (
            ("expected_reference_ppm", self.expected_reference_ppm),
            ("observed_reference_ppm", self.observed_reference_ppm),
            (
                "solvent_interference_tolerance_ppm",
                self.solvent_interference_tolerance_ppm,
            ),
        ):
            if value < 0.0 or not isfinite(value):
                raise ValueError(f"{name} must be finite and nonnegative")
        if any(value < 0.0 or not isfinite(value) for value in self.solvent_residual_peaks_ppm):
            raise ValueError("solvent residual shifts must be finite and nonnegative")

    @property
    def reference_correction_ppm(self) -> float:
        return self.expected_reference_ppm - self.observed_reference_ppm

    def to_dict(self) -> dict[str, object]:
        return {
            "method_id": self.method_id,
            "spectrometer_frequency_MHz": self.spectrometer_frequency_MHz,
            "solvent_id": self.solvent_id,
            "solvent_residual_peaks_ppm": list(self.solvent_residual_peaks_ppm),
            "reference_id": self.reference_id,
            "expected_reference_ppm": self.expected_reference_ppm,
            "observed_reference_ppm": self.observed_reference_ppm,
            "reference_correction_ppm": self.reference_correction_ppm,
            "solvent_interference_tolerance_ppm": (self.solvent_interference_tolerance_ppm),
        }


@dataclass(frozen=True)
class NMRStickLine:
    chemical_shift_ppm: float
    relative_intensity: float

    def to_dict(self) -> dict[str, float]:
        return {
            "chemical_shift_ppm": self.chemical_shift_ppm,
            "relative_intensity": self.relative_intensity,
        }


@dataclass(frozen=True)
class ProtonNMRSignalResult:
    species_id: str
    signal_id: str
    corrected_chemical_shift_ppm: float
    proton_count: int
    multiplicity: NMRMultiplicity
    coupling_constants_Hz: tuple[float, ...]
    assignment: str
    raw_integral: float
    normalized_integral: float
    lines: tuple[NMRStickLine, ...]
    solvent_interference: bool
    overlap_signal_ids: tuple[str, ...]
    second_order_risk: bool
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "species_id": self.species_id,
            "signal_id": self.signal_id,
            "corrected_chemical_shift_ppm": self.corrected_chemical_shift_ppm,
            "proton_count": self.proton_count,
            "multiplicity": self.multiplicity,
            "coupling_constants_Hz": list(self.coupling_constants_Hz),
            "assignment": self.assignment,
            "raw_integral": self.raw_integral,
            "normalized_integral": self.normalized_integral,
            "lines": [line.to_dict() for line in self.lines],
            "solvent_interference": self.solvent_interference,
            "overlap_signal_ids": list(self.overlap_signal_ids),
            "second_order_risk": self.second_order_risk,
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class ProtonNMRReport:
    model_id: str
    method: ProtonNMRMethodSpec
    species_amounts_mol: dict[str, float]
    total_integral: float
    signals: tuple[ProtonNMRSignalResult, ...]
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "model_id": self.model_id,
            "method": self.method.to_dict(),
            "species_amounts_mol": dict(self.species_amounts_mol),
            "total_integral": self.total_integral,
            "signals": [signal.to_dict() for signal in self.signals],
            "warnings": list(self.warnings),
        }


def simulate_proton_nmr(
    signals: Sequence[ProtonNMRSignalSpec],
    *,
    species_amounts_mol: Mapping[str, float],
    method: ProtonNMRMethodSpec,
) -> ProtonNMRReport:
    if not signals:
        raise ValueError("at least one NMR signal is required")
    signal_ids = [signal.signal_id for signal in signals]
    if len(signal_ids) != len(set(signal_ids)):
        raise ValueError("NMR signal ids must be unique")
    amounts = {str(key): float(value) for key, value in species_amounts_mol.items()}
    if any(value < 0.0 or not isfinite(value) for value in amounts.values()):
        raise ValueError("species amounts must be finite and nonnegative")
    missing = {signal.species_id for signal in signals} - set(amounts)
    if missing:
        raise ValueError(f"species amounts missing NMR species: {sorted(missing)}")
    raw_integrals = {
        signal.signal_id: amounts[signal.species_id] * signal.proton_count * signal.response_factor
        for signal in signals
    }
    total_integral = sum(raw_integrals.values())
    corrected_shifts = {
        signal.signal_id: signal.chemical_shift_ppm + method.reference_correction_ppm
        for signal in signals
    }
    results: list[ProtonNMRSignalResult] = []
    report_warnings: set[str] = set()
    for signal in signals:
        shift = corrected_shifts[signal.signal_id]
        solvent_interference = any(
            abs(shift - solvent_shift) <= method.solvent_interference_tolerance_ppm
            for solvent_shift in method.solvent_residual_peaks_ppm
        )
        overlap_ids = tuple(
            other.signal_id
            for other in signals
            if other.signal_id != signal.signal_id
            and abs(shift - corrected_shifts[other.signal_id])
            <= 0.5
            * (signal.line_width_Hz + other.line_width_Hz)
            / method.spectrometer_frequency_MHz
        )
        second_order = any(
            _second_order_pair_risk(signal, other, corrected_shifts, method)
            for other in signals
            if other.signal_id != signal.signal_id
        )
        warnings: list[str] = []
        if solvent_interference:
            warnings.append("solvent_residual_interference")
        if overlap_ids:
            warnings.append("signal_overlap")
        if second_order:
            warnings.append("second_order_splitting_risk")
        if signal.exchangeable:
            warnings.append("exchangeable_proton_shift_and_width_variable")
        if signal.multiplicity == "m":
            warnings.append("unresolved_multiplet")
        report_warnings.update(warnings)
        results.append(
            ProtonNMRSignalResult(
                species_id=signal.species_id,
                signal_id=signal.signal_id,
                corrected_chemical_shift_ppm=shift,
                proton_count=signal.proton_count,
                multiplicity=signal.multiplicity,
                coupling_constants_Hz=signal.coupling_constants_Hz,
                assignment=signal.assignment,
                raw_integral=raw_integrals[signal.signal_id],
                normalized_integral=(
                    0.0
                    if total_integral <= 0.0
                    else raw_integrals[signal.signal_id] / total_integral
                ),
                lines=_first_order_lines(signal, shift, method.spectrometer_frequency_MHz),
                solvent_interference=solvent_interference,
                overlap_signal_ids=overlap_ids,
                second_order_risk=second_order,
                warnings=tuple(warnings),
            )
        )
    return ProtonNMRReport(
        model_id="first_order_proton_nmr_assignments_v1",
        method=method,
        species_amounts_mol=amounts,
        total_integral=total_integral,
        signals=tuple(results),
        warnings=tuple(sorted(report_warnings)),
    )


def _first_order_lines(
    signal: ProtonNMRSignalSpec,
    corrected_shift_ppm: float,
    frequency_MHz: float,
) -> tuple[NMRStickLine, ...]:
    if signal.multiplicity in {"s", "br_s", "m"}:
        return (NMRStickLine(corrected_shift_ppm, 1.0),)
    if signal.multiplicity == "dd":
        offsets = [(0.0, 1.0)]
        for coupling in signal.coupling_constants_Hz:
            offsets = [
                (offset + direction * coupling / 2.0, intensity)
                for offset, intensity in offsets
                for direction in (-1.0, 1.0)
            ]
    else:
        split_order = {"d": 1, "t": 2, "q": 3, "quint": 4}[signal.multiplicity]
        coupling = signal.coupling_constants_Hz[0]
        coefficients = _pascal_row(split_order)
        offsets = [
            ((index - split_order / 2.0) * coupling, float(coefficient))
            for index, coefficient in enumerate(coefficients)
        ]
    total_intensity = sum(intensity for _, intensity in offsets)
    return tuple(
        NMRStickLine(
            chemical_shift_ppm=corrected_shift_ppm + offset_Hz / frequency_MHz,
            relative_intensity=intensity / total_intensity,
        )
        for offset_Hz, intensity in sorted(offsets)
    )


def _pascal_row(order: int) -> tuple[int, ...]:
    row = [1]
    for _ in range(order):
        row = [1, *[row[index] + row[index + 1] for index in range(len(row) - 1)], 1]
    return tuple(row)


def _second_order_pair_risk(
    signal: ProtonNMRSignalSpec,
    other: ProtonNMRSignalSpec,
    corrected_shifts: Mapping[str, float],
    method: ProtonNMRMethodSpec,
) -> bool:
    couplings = signal.coupling_constants_Hz + other.coupling_constants_Hz
    if not couplings:
        return False
    separation_Hz = (
        abs(corrected_shifts[signal.signal_id] - corrected_shifts[other.signal_id])
        * method.spectrometer_frequency_MHz
    )
    return separation_Hz / max(couplings) < 10.0


def _positive(value: float, field_name: str) -> None:
    if value <= 0.0 or not isfinite(value):
        raise ValueError(f"{field_name} must be positive and finite")


__all__ = [
    "NMRStickLine",
    "ProtonNMRMethodSpec",
    "ProtonNMRReport",
    "ProtonNMRSignalResult",
    "ProtonNMRSignalSpec",
    "simulate_proton_nmr",
]
