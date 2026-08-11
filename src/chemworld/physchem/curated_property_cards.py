"""Curated-property model cards for ChemWorld."""

from __future__ import annotations

from chemworld.physchem.maturity import MaturityLevel, ModelCard, ValidationEvidence

_REFERENCE_NOTES = (
    "reference_repos/chemicals/chemicals/vapor_pressure.py: Psat_data_Perrys2_8",
    "reference_repos/chemicals/chemicals/dippr.py: EQ101 vapor-pressure equation",
    "reference_repos/chemicals/chemicals/heat_capacity.py: Cp_data_Poling",
    "reference_repos/thermo/thermo/heat_capacity.py: POLING_POLY uses R-scaled DIPPR100",
)


def curated_property_model_cards() -> tuple[ModelCard, ...]:
    """Return maturity metadata for the curated property slice."""

    return (
        ModelCard(
            model_id="curated_dippr101_poling_property_subset",
            module_id="properties",
            title="Curated DIPPR101 Vapor Pressure And Poling Ideal-Gas Cp",
            maturity=MaturityLevel.REFERENCE_VALIDATED,
            summary=(
                "Small ChemWorld-local property package for water, ethanol, "
                "acetone, toluene, methane, and carbon dioxide."
            ),
            equations=(
                "DIPPR101 Psat = exp(A + B/T + C*ln(T) + D*T**E)",
                "Poling/DIPPR100 Cp_ig = R*(a0 + a1*T + a2*T**2 + a3*T**3 + a4*T**4)",
                "DeltaH_sensible = integral(Cp_ig dT)",
            ),
            assumptions=(
                "Vapor-pressure coefficients are used only inside their table "
                "temperature bounds.",
                "Poling ideal-gas heat capacity is independent of pressure.",
                "Sensible enthalpy currently integrates ideal-gas Cp only; no "
                "phase-change path is inferred automatically.",
            ),
            validity_limits=(
                "Each component carries its own DIPPR101 vapor-pressure "
                "temperature interval.",
                "Each component carries its own Poling ideal-gas heat-capacity "
                "temperature interval.",
                "The curated package is deliberately limited to six common "
                "compounds until additional cases are independently checked.",
            ),
            failure_modes=(
                "Out-of-range property calls can extrapolate if the caller "
                "selects warn or ignore validity policy.",
                "Near-critical and condensed-phase enthalpy behavior is outside "
                "this model card.",
                "The package is not a general property database and does not "
                "choose among competing correlations.",
            ),
            units={
                "temperature": "K",
                "pressure": "Pa",
                "heat_capacity": "J/(mol*K)",
                "sensible_enthalpy": "J/mol",
            },
            reference_reading=_REFERENCE_NOTES,
            validation_evidence=(
                ValidationEvidence(
                    evidence_id="chemicals-curated-dippr101-vapor-pressure",
                    evidence_type="optional_reference_test",
                    description=(
                        "Checks curated DIPPR101 vapor-pressure values against "
                        "chemicals.dippr.EQ101 and Psat_data_Perrys2_8."
                    ),
                    status="implemented",
                    reference_backend="chemicals",
                    command_or_path=(
                        "tests/reference/test_optional_reference_backends.py"
                    ),
                    tolerance="rtol=1e-12",
                ),
                ValidationEvidence(
                    evidence_id="chemicals-curated-poling-cp-enthalpy",
                    evidence_type="optional_reference_test",
                    description=(
                        "Checks curated R-scaled Poling ideal-gas Cp and "
                        "sensible enthalpy integrals against chemicals.dippr.EQ100."
                    ),
                    status="implemented",
                    reference_backend="chemicals",
                    command_or_path=(
                        "tests/reference/test_optional_reference_backends.py"
                    ),
                    tolerance="rtol=1e-12",
                ),
                ValidationEvidence(
                    evidence_id="curated-property-temperature-domain-guards",
                    evidence_type="failure_domain_test",
                    description=(
                        "Checks that every curated DIPPR101 and Poling correlation "
                        "fails closed outside its declared temperature bounds when "
                        "the strict validity policy is selected."
                    ),
                    status="implemented",
                    reference_backend="chemicals",
                    command_or_path="tests/test_physchem_properties.py",
                    tolerance="exact outside-validity-domain rejection",
                ),
            ),
            model_limit_notes=(
                "This is a reference-validated curated slice, not a vendored "
                "copy of the chemicals or thermo databases.",
            ),
            intended_use=(
                "Benchmark property fixtures with transparent provenance.",
                "Regression cases for future professional property backends.",
                "Teaching examples where coefficients and unit conversions "
                "must remain inspectable.",
            ),
        ),
    )




__all__ = [
    "_REFERENCE_NOTES",
    "curated_property_model_cards",
]
