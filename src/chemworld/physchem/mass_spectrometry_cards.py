"""Model card for compact mass-spectrometry evidence."""

from __future__ import annotations

from chemworld.physchem.maturity import MaturityLevel, ModelCard, ValidationEvidence


def mass_spectrometry_model_cards() -> tuple[ModelCard, ...]:
    return (
        ModelCard(
            model_id="small_formula_isotope_fragment_ms_v1",
            module_id="spectroscopy_instruments",
            title="Small-Formula Isotope Envelopes And Fragment Metadata",
            maturity=MaturityLevel.REFERENCE_VALIDATED,
            summary=(
                "Natural-abundance nominal isotope envelopes for common "
                "small-molecule elements, curated fragment-ion assignments, "
                "and amount-scaled detector response uncertainty."
            ),
            equations=(
                "molecular isotope probabilities are repeated multinomial convolutions",
                "nominal shift = sum(A_isotope - A_light)",
                "m/z = exact neutral isotope mass / abs(charge)",
                "relative intensity = 100 probability/base-peak probability",
                "response mean = response factor * analyte amount",
                "response standard deviation = mean * detector RSD",
            ),
            assumptions=(
                "Natural isotope abundances are fixed curated constants for H, "
                "C, N, O, F, Si, P, S, Cl, and Br.",
                "Nominal-shift isobars are grouped and assigned a probability-"
                "weighted exact-mass center.",
                "Fragment formulas, relative intensities, neutral losses, and "
                "assignments are curated metadata, not predicted fragmentation.",
                "Detector uncertainty is a declared relative standard deviation.",
            ),
            validity_limits=(
                "Formula atom counts must be integers and total atoms are "
                "limited by a caller-controlled compact-envelope bound.",
                "Only elements in the curated isotope table are supported.",
                "Charge scales neutral exact mass; electron/proton/adduct mass "
                "corrections are not automatically applied.",
                "Low-resolution nominal envelopes are intended for small formulas.",
            ),
            failure_modes=(
                "Unsupported elements, zero charge, oversized formulas, and "
                "fully pruned envelopes fail early.",
                "Fragment monoisotopic mass above the parent mass fails.",
                "Missing fragment metadata and detector RSD above 20% produce warnings.",
            ),
            units={
                "exact mass/mass-to-charge": "u; u/e (reported as m/z)",
                "abundance/relative intensity/RSD": "fraction; percent; fraction",
                "analyte amount": "mol",
                "detector response": "declared detector response units",
            },
            reference_reading=(
                "IUPAC natural isotope-abundance and exact-isotope-mass conventions",
                "Binomial/multinomial isotope-envelope construction for small "
                "organic, chlorine-, bromine-, sulfur-, and silicon-containing formulas",
                "NIST-style mass-spectrum reporting of molecular ions, fragment "
                "assignments, neutral losses, and relative intensities",
            ),
            validation_evidence=(
                ValidationEvidence(
                    evidence_id="carbon-chlorine-bromine-isotope-patterns",
                    evidence_type="analytical_test",
                    description=(
                        "Checks C2 M+1 abundance including deuterium and the "
                        "diagnostic Cl/Br M:M+2 natural-abundance ratios."
                    ),
                    status="implemented",
                    command_or_path="tests/test_mass_spectrometry.py",
                    tolerance="2% relative on compact abundance ratios",
                ),
                ValidationEvidence(
                    evidence_id="fragment-and-detector-uncertainty-contract",
                    evidence_type="unit_test",
                    description=(
                        "Checks fragment m/z/neutral loss, parent mass bounds, "
                        "response mean/RSD, warnings, pruning, and unsupported elements."
                    ),
                    status="implemented",
                    command_or_path="tests/test_mass_spectrometry.py",
                    tolerance="pytest.approx response and exact failure flags",
                ),
            ),
            model_limit_notes=(
                "Reference validation denotes an auditable isotope/fragment "
                "evidence contract, not a quantum fragmentation predictor.",
                "Adduct chemistry, ion-source competition, metastable ions, "
                "high-resolution peak shapes, and library matching are absent.",
            ),
            intended_use=(
                "Small-molecule formula and halogen-pattern benchmark tasks.",
                "Agent reasoning over molecular ions, curated fragments, isotope "
                "evidence, and detector uncertainty.",
            ),
        ),
    )


__all__ = ["mass_spectrometry_model_cards"]
