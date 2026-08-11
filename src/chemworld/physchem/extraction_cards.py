"""Model cards for activity-corrected extraction trains."""

from __future__ import annotations

from chemworld.physchem.maturity import MaturityLevel, ModelCard, ValidationEvidence


def extraction_unit_model_cards() -> tuple[ModelCard, ...]:
    return (
        ModelCard(
            model_id="activity_corrected_extraction_train_v1",
            module_id="separations",
            title="Activity-Corrected Multistage Extraction And Wash Train",
            maturity=MaturityLevel.REFERENCE_VALIDATED,
            summary=(
                "Fresh-solvent extraction stages and aqueous wash contacts "
                "with composition-dependent distribution coefficients, "
                "explicit entrainment, and recovery/purity ledgers."
            ),
            equations=(
                "D_i = K_i^0 gamma_i^aqueous / gamma_i^organic",
                "n_i^org,eq = n_i D_i V_org / (D_i V_org + V_aq)",
                "n_i^org = n_i^org,in + eta(n_i^org,eq - n_i^org,in)",
                "n_i^entrained = f_entrainment n_i^aqueous",
                "recovery_target = n_target,extract / n_target,feed",
                "purity_target = n_target,extract / sum_i n_i,extract",
            ),
            assumptions=(
                "Intrinsic partition coefficients and provenance are supplied "
                "by the scenario or property package.",
                "Aqueous and organic activity models use the same tracked solute component set.",
                "Each extraction stage receives fresh organic solvent; wash "
                "contacts receive fresh aqueous liquid.",
                "Stage efficiency is a linear approach to the calculated equilibrium split.",
                "Entrainment transfers a declared fraction of aqueous solute "
                "and aqueous contact volume with the organic outlet.",
            ),
            validity_limits=(
                "All intrinsic partition coefficients and contact volumes "
                "must be positive and finite.",
                "Tracked amounts represent solutes; bulk solvent composition, "
                "density, mutual solubility, and phase-volume change are not "
                "predicted.",
                "The fixed-point solve is intended for small benchmark "
                "mixtures with supported activity-coefficient models.",
            ),
            failure_modes=(
                "Component mismatches, missing provenance, invalid volumes, "
                "and invalid efficiency/entrainment controls fail early.",
                "A distribution fixed point that reaches the iteration limit "
                "is returned with converged=false and a stage warning.",
                "Loss of liquid-liquid stability is not automatically "
                "reconciled into a single-phase state.",
            ),
            units={
                "component amount": "mol",
                "phase/contact volume": "L",
                "temperature": "K",
                "partition/distribution/activity coefficients": "dimensionless",
                "efficiency/entrainment/recovery/purity": "dimensionless",
            },
            reference_reading=(
                "reference_repos/phasepy/phasepy/equilibrium: activity-model "
                "and liquid-liquid equilibrium workflow conventions",
                "reference_repos/thermo/thermo/activity.py: excess-Gibbs and "
                "activity-coefficient phase-model contracts",
                "IDAES unit-model conventions: component material balances "
                "and explicit inlet/outlet phase streams",
            ),
            validation_evidence=(
                ValidationEvidence(
                    evidence_id="fresh-solvent-extraction-analytical-recovery",
                    evidence_type="unit_test",
                    description=(
                        "Compares two ideal fresh-solvent contacts with the "
                        "closed-form remaining-fraction product."
                    ),
                    status="implemented",
                    command_or_path="tests/test_extraction_units.py",
                    tolerance="pytest.approx and material residual < 1e-12",
                ),
                ValidationEvidence(
                    evidence_id="activity-corrected-distribution-and-wash",
                    evidence_type="unit_test",
                    description=(
                        "Checks Margules correction of D, wash-driven impurity "
                        "rejection, target loss, entrainment, stage sequence, "
                        "and train-wide component balance."
                    ),
                    status="implemented",
                    command_or_path="tests/test_extraction_units.py",
                    tolerance="material residual < 1e-12",
                ),
            ),
            model_limit_notes=(
                "Reference validation covers the mass-balanced extraction "
                "train, not a rigorous electrolyte/multiphase flowsheet model.",
                "Hydrodynamics, emulsion formation, solvent saturation, and "
                "rate-based mass transfer remain outside this slice.",
            ),
            intended_use=(
                "Solvent-selection and wash-sequence benchmark tasks.",
                "Agent planning over recovery, purity, solvent use, and entrainment tradeoffs.",
            ),
        ),
    )


__all__ = ["extraction_unit_model_cards"]
