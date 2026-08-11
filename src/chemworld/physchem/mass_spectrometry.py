"""Small-formula isotope envelopes and simple MS fragmentation metadata."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from chemworld.physchem.elements import parse_formula


@dataclass(frozen=True)
class IsotopeSpec:
    mass_number: int
    exact_mass_u: float
    abundance: float


ISOTOPES: dict[str, tuple[IsotopeSpec, ...]] = {
    "H": (IsotopeSpec(1, 1.00782503223, 0.999885), IsotopeSpec(2, 2.01410177812, 0.000115)),
    "C": (IsotopeSpec(12, 12.0, 0.9893), IsotopeSpec(13, 13.00335483507, 0.0107)),
    "N": (IsotopeSpec(14, 14.00307400443, 0.99636), IsotopeSpec(15, 15.00010889888, 0.00364)),
    "O": (
        IsotopeSpec(16, 15.99491461957, 0.99757),
        IsotopeSpec(17, 16.99913175650, 0.00038),
        IsotopeSpec(18, 17.99915961286, 0.00205),
    ),
    "F": (IsotopeSpec(19, 18.99840316273, 1.0),),
    "Si": (
        IsotopeSpec(28, 27.97692653465, 0.92223),
        IsotopeSpec(29, 28.97649466490, 0.04685),
        IsotopeSpec(30, 29.973770136, 0.03092),
    ),
    "P": (IsotopeSpec(31, 30.97376199842, 1.0),),
    "S": (
        IsotopeSpec(32, 31.9720711744, 0.9499),
        IsotopeSpec(33, 32.9714589098, 0.0075),
        IsotopeSpec(34, 33.967867004, 0.0425),
        IsotopeSpec(36, 35.96708071, 0.0001),
    ),
    "Cl": (IsotopeSpec(35, 34.968852682, 0.7578), IsotopeSpec(37, 36.965902602, 0.2422)),
    "Br": (IsotopeSpec(79, 78.9183376, 0.5069), IsotopeSpec(81, 80.9162897, 0.4931)),
}


@dataclass(frozen=True)
class FragmentIonSpec:
    fragment_id: str
    formula: str
    charge: int
    relative_intensity: float
    assignment: str
    neutral_loss: str | None = None

    def __post_init__(self) -> None:
        if not self.fragment_id or not self.formula or not self.assignment:
            raise ValueError("fragment id, formula, and assignment cannot be empty")
        if self.charge == 0:
            raise ValueError("fragment charge cannot be zero")
        if not 0.0 < self.relative_intensity <= 100.0 or not isfinite(self.relative_intensity):
            raise ValueError("fragment relative_intensity must be in (0, 100]")
        _integer_formula(self.formula)

    def to_dict(self) -> dict[str, object]:
        return {
            "fragment_id": self.fragment_id,
            "formula": self.formula,
            "charge": self.charge,
            "relative_intensity": self.relative_intensity,
            "assignment": self.assignment,
            "neutral_loss": self.neutral_loss,
        }


@dataclass(frozen=True)
class MassSpectrumAnalyteSpec:
    analyte_id: str
    formula: str
    molecular_ion_charge: int
    ionization_method: str
    fragments: tuple[FragmentIonSpec, ...]
    detector_response_factor: float
    detector_relative_standard_deviation: float
    provenance_id: str

    def __post_init__(self) -> None:
        if not self.analyte_id or not self.ionization_method or not self.provenance_id:
            raise ValueError("analyte, ionization, and provenance ids cannot be empty")
        if self.molecular_ion_charge == 0:
            raise ValueError("molecular ion charge cannot be zero")
        _integer_formula(self.formula)
        _positive(self.detector_response_factor, "detector_response_factor")
        if not 0.0 <= self.detector_relative_standard_deviation <= 1.0:
            raise ValueError("detector_relative_standard_deviation must be in [0, 1]")
        fragment_ids = [fragment.fragment_id for fragment in self.fragments]
        if len(fragment_ids) != len(set(fragment_ids)):
            raise ValueError("fragment ids must be unique")

    def to_dict(self) -> dict[str, object]:
        return {
            "analyte_id": self.analyte_id,
            "formula": self.formula,
            "molecular_ion_charge": self.molecular_ion_charge,
            "ionization_method": self.ionization_method,
            "fragments": [fragment.to_dict() for fragment in self.fragments],
            "detector_response_factor": self.detector_response_factor,
            "detector_relative_standard_deviation": (self.detector_relative_standard_deviation),
            "provenance_id": self.provenance_id,
        }


@dataclass(frozen=True)
class IsotopeEnvelopePeak:
    nominal_mass_shift: int
    exact_mass_u: float
    mass_to_charge: float
    abundance: float
    relative_intensity: float

    def to_dict(self) -> dict[str, float | int]:
        return {
            "nominal_mass_shift": self.nominal_mass_shift,
            "exact_mass_u": self.exact_mass_u,
            "mass_to_charge": self.mass_to_charge,
            "abundance": self.abundance,
            "relative_intensity": self.relative_intensity,
        }


@dataclass(frozen=True)
class FragmentIonResult:
    fragment_id: str
    formula: str
    mass_to_charge: float
    charge: int
    relative_intensity: float
    assignment: str
    neutral_loss: str | None

    def to_dict(self) -> dict[str, object]:
        return {
            "fragment_id": self.fragment_id,
            "formula": self.formula,
            "mass_to_charge": self.mass_to_charge,
            "charge": self.charge,
            "relative_intensity": self.relative_intensity,
            "assignment": self.assignment,
            "neutral_loss": self.neutral_loss,
        }


@dataclass(frozen=True)
class MassSpectrumReport:
    model_id: str
    analyte_id: str
    formula: str
    ionization_method: str
    molecular_ion_charge: int
    isotope_envelope: tuple[IsotopeEnvelopePeak, ...]
    fragments: tuple[FragmentIonResult, ...]
    analyte_amount_mol: float
    detector_response_mean: float
    detector_response_standard_deviation: float
    detector_relative_standard_deviation: float
    warnings: tuple[str, ...]
    provenance_id: str

    def to_dict(self) -> dict[str, object]:
        return {
            "model_id": self.model_id,
            "analyte_id": self.analyte_id,
            "formula": self.formula,
            "ionization_method": self.ionization_method,
            "molecular_ion_charge": self.molecular_ion_charge,
            "isotope_envelope": [peak.to_dict() for peak in self.isotope_envelope],
            "fragments": [fragment.to_dict() for fragment in self.fragments],
            "analyte_amount_mol": self.analyte_amount_mol,
            "detector_response_mean": self.detector_response_mean,
            "detector_response_standard_deviation": (self.detector_response_standard_deviation),
            "detector_relative_standard_deviation": (self.detector_relative_standard_deviation),
            "warnings": list(self.warnings),
            "provenance_id": self.provenance_id,
        }


def isotope_envelope(
    formula: str,
    *,
    charge: int = 1,
    minimum_abundance: float = 1.0e-8,
    maximum_peaks: int = 12,
    maximum_atoms: int = 100,
) -> tuple[IsotopeEnvelopePeak, ...]:
    composition = _integer_formula(formula)
    if charge == 0:
        raise ValueError("charge cannot be zero")
    if minimum_abundance <= 0.0 or not isfinite(minimum_abundance):
        raise ValueError("minimum_abundance must be positive and finite")
    if maximum_peaks <= 0 or maximum_atoms <= 0:
        raise ValueError("maximum_peaks and maximum_atoms must be positive")
    if sum(composition.values()) > maximum_atoms:
        raise ValueError("formula exceeds maximum_atoms for compact isotope envelope")
    unsupported = set(composition) - set(ISOTOPES)
    if unsupported:
        raise ValueError(f"isotope data unavailable for elements: {sorted(unsupported)}")
    states: list[tuple[int, float, float]] = [(0, 0.0, 1.0)]
    for element, count in composition.items():
        isotopes = ISOTOPES[element]
        light_mass_number = isotopes[0].mass_number
        for _ in range(count):
            states = [
                (
                    shift + isotope.mass_number - light_mass_number,
                    mass + isotope.exact_mass_u,
                    probability * isotope.abundance,
                )
                for shift, mass, probability in states
                for isotope in isotopes
                if probability * isotope.abundance >= minimum_abundance * 0.01
            ]
    grouped: dict[int, tuple[float, float]] = {}
    for shift, mass, probability in states:
        probability_sum, mass_moment = grouped.get(shift, (0.0, 0.0))
        grouped[shift] = (
            probability_sum + probability,
            mass_moment + probability * mass,
        )
    retained = [
        (shift, probability, moment / probability)
        for shift, (probability, moment) in grouped.items()
        if probability >= minimum_abundance
    ]
    retained.sort(key=lambda item: item[0])
    retained = retained[:maximum_peaks]
    total_probability = sum(item[1] for item in retained)
    if total_probability <= 0.0:
        raise ValueError("isotope envelope was fully pruned")
    base_probability = max(item[1] for item in retained)
    return tuple(
        IsotopeEnvelopePeak(
            nominal_mass_shift=shift,
            exact_mass_u=mass,
            mass_to_charge=mass / abs(charge),
            abundance=probability / total_probability,
            relative_intensity=100.0 * probability / base_probability,
        )
        for shift, probability, mass in retained
    )


def simulate_mass_spectrum(
    analyte: MassSpectrumAnalyteSpec,
    *,
    analyte_amount_mol: float,
    minimum_isotope_abundance: float = 1.0e-8,
) -> MassSpectrumReport:
    _nonnegative(analyte_amount_mol, "analyte_amount_mol")
    envelope = isotope_envelope(
        analyte.formula,
        charge=analyte.molecular_ion_charge,
        minimum_abundance=minimum_isotope_abundance,
    )
    parent_monoisotopic_mass = envelope[0].exact_mass_u
    fragment_results: list[FragmentIonResult] = []
    warnings: list[str] = []
    for fragment in analyte.fragments:
        fragment_envelope = isotope_envelope(fragment.formula, charge=fragment.charge)
        fragment_mass = fragment_envelope[0].exact_mass_u
        if fragment_mass > parent_monoisotopic_mass + 1.0e-8:
            raise ValueError("fragment monoisotopic mass cannot exceed molecular ion mass")
        fragment_results.append(
            FragmentIonResult(
                fragment_id=fragment.fragment_id,
                formula=fragment.formula,
                mass_to_charge=fragment_envelope[0].mass_to_charge,
                charge=fragment.charge,
                relative_intensity=fragment.relative_intensity,
                assignment=fragment.assignment,
                neutral_loss=fragment.neutral_loss,
            )
        )
    if not fragment_results:
        warnings.append("no_fragmentation_metadata")
    if analyte.detector_relative_standard_deviation > 0.20:
        warnings.append("high_detector_response_uncertainty")
    response_mean = analyte.detector_response_factor * analyte_amount_mol
    return MassSpectrumReport(
        model_id="small_formula_isotope_fragment_ms_v1",
        analyte_id=analyte.analyte_id,
        formula=analyte.formula,
        ionization_method=analyte.ionization_method,
        molecular_ion_charge=analyte.molecular_ion_charge,
        isotope_envelope=envelope,
        fragments=tuple(fragment_results),
        analyte_amount_mol=analyte_amount_mol,
        detector_response_mean=response_mean,
        detector_response_standard_deviation=(
            response_mean * analyte.detector_relative_standard_deviation
        ),
        detector_relative_standard_deviation=(analyte.detector_relative_standard_deviation),
        warnings=tuple(warnings),
        provenance_id=analyte.provenance_id,
    )


def _integer_formula(formula: str) -> dict[str, int]:
    parsed = parse_formula(formula)
    result: dict[str, int] = {}
    for element, count in parsed.items():
        rounded = round(count)
        if abs(count - rounded) > 1.0e-12:
            raise ValueError("isotope envelopes require integer atom counts")
        result[element] = rounded
    return result


def _positive(value: float, field_name: str) -> None:
    if value <= 0.0 or not isfinite(value):
        raise ValueError(f"{field_name} must be positive and finite")


def _nonnegative(value: float, field_name: str) -> None:
    if value < 0.0 or not isfinite(value):
        raise ValueError(f"{field_name} must be nonnegative and finite")


__all__ = [
    "FragmentIonResult",
    "FragmentIonSpec",
    "IsotopeEnvelopePeak",
    "MassSpectrumAnalyteSpec",
    "MassSpectrumReport",
    "isotope_envelope",
    "simulate_mass_spectrum",
]
