"""Model cards for separated two-phase flow correlations."""

from __future__ import annotations

from chemworld.physchem.maturity import MaturityLevel, ModelCard, ValidationEvidence


def two_phase_flow_model_cards() -> tuple[ModelCard, ...]:
    return (
        ModelCard(
            model_id="lockhart_martinelli_chisholm_horizontal_v1",
            module_id="transport",
            title="Horizontal Lockhart-Martinelli Two-Phase Pressure Drop",
            maturity=MaturityLevel.REFERENCE_VALIDATED,
            summary=(
                "Separated gas-liquid frictional pressure drop using the "
                "Lockhart-Martinelli parameter and Chisholm regime constants, "
                "with all single-phase anchors exposed."
            ),
            equations=(
                "X^2 = DeltaP_liquid / DeltaP_vapor",
                "phi_l^2 = 1 + C/X + 1/X^2",
                "DeltaP_two_phase = phi_l^2 DeltaP_liquid",
                "f_D = 64/Re for Re < Re_c; 0.184 Re^-0.2 otherwise",
                "C = 5, 12, 10, or 20 for LL, LT, TL, or TT regimes",
            ),
            assumptions=(
                "Steady adiabatic two-component gas-liquid flow in a smooth "
                "horizontal circular pipe.",
                "Each phase uses its superficial velocity and the original "
                "correlation's friction-factor convention.",
                "The result is frictional pressure drop only; acceleration and "
                "static-head terms are absent.",
            ),
            validity_limits=(
                "Vapor quality must be strictly between zero and one.",
                "Inclination is restricted to zero and pipe roughness is not a model input.",
                "Qualities outside 0.05-0.95 and diameters below 3 mm emit "
                "endpoint or microchannel warnings.",
                "The empirical correlation has regime-dependent uncertainty "
                "and is not a mechanistic flow-pattern solver.",
            ),
            failure_modes=(
                "Nonpositive flow, properties, diameter, length, or transition "
                "Reynolds number fail early.",
                "Single-phase quality endpoints fail rather than entering a "
                "singular Martinelli calculation.",
                "Inclined-flow requests fail instead of silently omitting gravity.",
            ),
            units={
                "mass flow": "kg/s",
                "density": "kg/m^3",
                "viscosity": "Pa s",
                "diameter/length": "m",
                "pressure drop": "Pa",
                "quality/Re/X/phi^2/C": "dimensionless",
            },
            reference_reading=(
                "reference_repos/fluids/fluids/two_phase.py: "
                "Lockhart_Martinelli implementation and validity notes",
                "Lockhart and Martinelli (1949), Chemical Engineering Progress 45(1), 39-48",
                "Chisholm (1967), International Journal of Heat and Mass Transfer 10, 1767-1778",
            ),
            validation_evidence=(
                ValidationEvidence(
                    evidence_id="fluids-lockhart-martinelli-reference",
                    evidence_type="optional_reference_test",
                    description=(
                        "Compares pressure drop against fluids.two_phase."
                        "Lockhart_Martinelli for the published example."
                    ),
                    status="implemented",
                    reference_backend="fluids",
                    command_or_path=("tests/reference/test_optional_reference_backends.py"),
                    tolerance="rtol=1e-12",
                ),
                ValidationEvidence(
                    evidence_id="lockhart-martinelli-regime-and-scaling",
                    evidence_type="unit_test",
                    description=(
                        "Checks Chisholm regime selection, multiplier closure, "
                        "linear length scaling, warnings, and invalid domains."
                    ),
                    status="implemented",
                    command_or_path="tests/test_two_phase_flow.py",
                    tolerance="pytest.approx local analytical tolerances",
                ),
            ),
            model_limit_notes=(
                "This reference-validated slice complements rather than "
                "relabels the existing homogeneous rollout proxy.",
                "Roughness, flow-pattern maps, acceleration, gravity, dryout, "
                "and critical-flow effects require separate models.",
            ),
            intended_use=(
                "Auditable horizontal two-phase pressure-cost calculations.",
                "Benchmark comparisons between homogeneous and separated-flow "
                "assumptions within the declared validity domain.",
            ),
        ),
    )


__all__ = ["two_phase_flow_model_cards"]
