"""Model card for diffusion-layer current limitation."""

from __future__ import annotations

from chemworld.physchem.maturity import MaturityLevel, ModelCard, ValidationEvidence


def electrochem_transport_model_cards() -> tuple[ModelCard, ...]:
    return (
        ModelCard(
            model_id="diffusion_layer_limiting_current_v1",
            module_id="electrochemistry",
            title="Diffusion-Layer Limiting Current And Bulk Depletion",
            maturity=MaturityLevel.PROFESSIONAL_CANDIDATE,
            summary=(
                "Planar stagnant-film limiting current coupled to an analytically "
                "integrated finite, well-mixed reactant reservoir and current-"
                "efficiency ledger."
            ),
            equations=(
                "k_m A = A D/delta",
                "i_lim = n F A D C_bulk/delta",
                "C_surface = C_bulk max(1 - i_demand/i_lim, 0)",
                "sub-limiting: dC/dt = -i_demand/(n F V)",
                "limiting: dC/dt = -(A D/(delta V)) C",
                "current efficiency = useful charge/applied charge",
            ),
            assumptions=(
                "A planar stagnant diffusion layer has constant thickness and diffusivity.",
                "The bulk electrolyte is a finite, perfectly mixed volume.",
                "Applied and optional kinetic current caps are constant during one call.",
                "Charge not assigned to the tracked useful reaction is reported "
                "as side-reaction charge rather than disappearing.",
            ),
            validity_limits=(
                "Positive electrode area, diffusivity, diffusion-layer thickness, "
                "electrolyte volume, and electron number are required.",
                "Migration, convection, porous electrodes, multiple reactants, and "
                "time-varying diffusion layers are not modeled.",
                "The analytical piecewise solution assumes constant physical properties.",
            ),
            failure_modes=(
                "Nonphysical geometry/properties and nonfinite current fail early.",
                "Initial or later diffusion limitation produces explicit status warnings.",
                "Current efficiency below 95% and bulk depletion above 90% are flagged.",
            ),
            units={
                "area/diffusivity/layer thickness/volume": "m^2; m^2/s; m; m^3",
                "concentration": "mol/m^3",
                "current/charge/time": "A; C; s",
                "mass-transfer volumetric rate": "m^3/s",
                "depletion/current efficiency": "dimensionless",
            },
            reference_reading=(
                "Nernst diffusion-layer limiting-current approximation",
                "Fick's first law for planar mass transfer and Faraday charge conversion",
                "Finite stirred-reservoir material balances with constant current "
                "followed by mass-transfer-limited exponential depletion",
            ),
            validation_evidence=(
                ValidationEvidence(
                    evidence_id="diffusion-limiting-current-plateau",
                    evidence_type="analytical_test",
                    description=(
                        "Checks i_lim=nFADC/delta, zero surface concentration at "
                        "the plateau, and fully limiting exponential bulk depletion."
                    ),
                    status="implemented",
                    command_or_path="tests/test_electrochem_transport.py",
                    tolerance="pytest.approx analytical solution",
                ),
                ValidationEvidence(
                    evidence_id="piecewise-depletion-current-efficiency",
                    evidence_type="analytical_test",
                    description=(
                        "Checks sub-limiting linear depletion, transition time, "
                        "kinetic cap, signed current, useful/side charge, and warnings."
                    ),
                    status="implemented",
                    command_or_path="tests/test_electrochem_transport.py",
                    tolerance="pytest.approx charge and concentration balances",
                ),
            ),
            model_limit_notes=(
                "Professional-candidate denotes an auditable transport/current "
                "ledger, not a multidimensional electrochemical transport solver.",
                "Double-layer charging, controller dynamics, electrolyte migration, "
                "gas evolution, and electrode morphology are separate slices.",
            ),
            intended_use=(
                "Mass-transfer-limited electrolysis benchmark tasks.",
                "Agent reasoning over current plateaus, depletion, useful charge, "
                "side reactions, and efficiency.",
            ),
        ),
    )


__all__ = ["electrochem_transport_model_cards"]
