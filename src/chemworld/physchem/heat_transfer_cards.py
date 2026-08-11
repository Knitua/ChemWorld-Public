"""Model cards for phase-aware equipment heat transfer."""

from __future__ import annotations

from chemworld.physchem.maturity import MaturityLevel, ModelCard, ValidationEvidence


def equipment_heat_transfer_model_cards() -> tuple[ModelCard, ...]:
    return (
        ModelCard(
            model_id="equipment_phase_change_heat_transfer_v1",
            module_id="transport",
            title="Phase-Aware Jacket, Coil, And Shell Heat Transfer",
            maturity=MaturityLevel.REFERENCE_VALIDATED,
            summary=(
                "Lumped equipment heat transfer with explicit jacket coverage "
                "or coil/shell geometry factors, asymptotic fouling resistance, "
                "phase-change plateaus, and signed sensible/latent ledgers."
            ),
            equations=(
                "R_f(t) = R_f,0 + (R_f,infinity - R_f,0)(1 - exp(-k_f t))",
                "1/U_fouled = 1/U_clean + R_f(t)",
                "UA_effective = U_fouled A F_surface",
                "T(t) = T_utility + (T_0 - T_utility) exp(-UA t/C)",
                "Q_latent = n_phase DeltaH_phase at T_sat",
                "Q_total = Q_sensible + Q_latent",
            ),
            assumptions=(
                "The process inventory is perfectly mixed with constant lumped "
                "heat capacity within each sensible segment.",
                "Utility temperature and effective conductance are constant during one contact.",
                "Jacket coverage and geometry correction factors are declared "
                "equipment-card inputs rather than hidden multipliers.",
                "Boiling and condensation occur isothermally at the declared "
                "saturation temperature until the phase inventory is exhausted.",
            ),
            validity_limits=(
                "Surface correction factors are bounded empirical inputs and "
                "require equipment-specific provenance.",
                "The fouling law is an asymptotic resistance model without "
                "deposit chemistry, shear removal, or cleaning cycles.",
                "One phase-change boundary and one lumped process inventory are "
                "supported per call.",
            ),
            failure_modes=(
                "Inconsistent utility direction for boiling or condensation "
                "fails before integration.",
                "Crossing a supplied saturation boundary with mode=none emits "
                "a warning and performs no phase conversion.",
                "Partial and exhausted phase inventories are explicit warnings.",
            ),
            units={
                "temperature": "K",
                "time": "s",
                "area": "m^2",
                "heat-transfer coefficient": "W/(m^2 K)",
                "fouling resistance": "m^2 K/W",
                "conductance/heat capacity": "W/K; J/K",
                "energy/rate": "J; W",
                "latent heat/phase amount": "J/mol; mol",
            },
            reference_reading=(
                "reference_repos/idaes-pse/idaes/models/unit_models/"
                "heat_exchanger.py: explicit U, area, driving force, and duty contracts",
                "reference_repos/idaes-pse/idaes/models/unit_models/"
                "heat_exchanger_ntu.py: conductance and energy-balance conventions",
                "reference_repos/fluids: equipment correction and heat-transfer "
                "correlation organization conventions",
            ),
            validation_evidence=(
                ValidationEvidence(
                    evidence_id="lumped-sensible-fouling-and-surface-corrections",
                    evidence_type="analytical_test",
                    description=(
                        "Checks exponential fouling growth, U degradation, and "
                        "explicit jacket/coil/shell conductance ordering."
                    ),
                    status="implemented",
                    command_or_path="tests/test_heat_transfer_units.py",
                    tolerance="pytest.approx analytical relations",
                ),
                ValidationEvidence(
                    evidence_id="boiling-condensation-energy-ledger",
                    evidence_type="unit_test",
                    description=(
                        "Checks signed boiling and condensation duties, phase "
                        "amounts, saturation handling, warnings, and exact "
                        "sensible-plus-latent closure."
                    ),
                    status="implemented",
                    command_or_path="tests/test_heat_transfer_units.py",
                    tolerance="energy residual <= 1e-12 J",
                ),
            ),
            model_limit_notes=(
                "Reference validation denotes an auditable equipment ledger, "
                "not a detailed boiling/condensation correlation package.",
                "Film coefficients, critical heat flux, flow regime maps, "
                "maldistribution, and distributed wall dynamics are external.",
            ),
            intended_use=(
                "Benchmark jacket, coil, condenser, and exchanger operations.",
                "Agent tradeoff studies involving fouling, phase inventory, "
                "thermal duty, and equipment corrections.",
            ),
        ),
    )


__all__ = ["equipment_heat_transfer_model_cards"]
