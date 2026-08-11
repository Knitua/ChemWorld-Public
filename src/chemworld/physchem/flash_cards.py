"""Model cards for material- and energy-balanced flash units."""

from __future__ import annotations

from chemworld.physchem.maturity import MaturityLevel, ModelCard, ValidationEvidence


def flash_unit_model_cards() -> tuple[ModelCard, ...]:
    """Return auditable cards for the implemented flash-unit slice."""

    return (
        ModelCard(
            model_id="tp_gamma_phi_flash_energy_balance_v1",
            module_id="separations",
            title="Fixed-TP Gamma-Phi Flash With Enthalpy Ledger",
            maturity=MaturityLevel.REFERENCE_VALIDATED,
            summary=(
                "Iterated fixed-temperature, fixed-pressure gamma-phi flash "
                "with an explicit component material split and feed/product "
                "enthalpy duty ledger."
            ),
            equations=(
                "K_i = gamma_i P_sat,i phi_i^l,ref Poynting_i / (phi_i^v P)",
                "sum_i z_i (K_i - 1) / (1 + beta (K_i - 1)) = 0",
                "L x_i + V y_i = F z_i",
                "Q = H_liquid + H_vapor - H_feed",
            ),
            assumptions=(
                "Temperature and pressure are prescribed; heat duty is the "
                "result rather than a solved temperature.",
                "Phase molar enthalpies are supplied at the declared state.",
                "Activity, fugacity, liquid-reference, and Poynting factors "
                "are explicit caller-controlled model inputs.",
                "The liquid-composition fixed point is damped by one half.",
            ),
            validity_limits=(
                "All components require positive vapor pressures and finite "
                "phase/feed molar enthalpies.",
                "The implementation performs a two-phase Rachford-Rice split "
                "or reports the corresponding single-phase endpoint.",
                "No EOS fugacity or caloric property package is selected "
                "automatically; callers must provide those factors and data.",
            ),
            failure_modes=(
                "Mismatched component mappings and nonfinite or nonpositive "
                "thermodynamic factors fail before iteration.",
                "A nonconverged gamma-phi fixed point is returned with "
                "converged=false and an explicit warning.",
                "Phase-stability, liquid-liquid splitting, critical states, "
                "and reactive flashes are outside this unit contract.",
            ),
            units={
                "temperature": "K",
                "pressure/vapor pressure": "Pa",
                "component amount": "mol",
                "molar enthalpy": "J/mol",
                "enthalpy/heat duty": "J",
                "composition/vapor fraction/K/gamma/phi/Poynting": "dimensionless",
            },
            reference_reading=(
                "reference_repos/chemicals/chemicals/rachford_rice.py: "
                "Rachford-Rice phase-split conventions",
                "reference_repos/thermo/thermo/flash/flash_base.py: "
                "fixed-TP flash workflow and phase-accounting conventions",
            ),
            validation_evidence=(
                ValidationEvidence(
                    evidence_id="tp-flash-material-energy-closure",
                    evidence_type="unit_test",
                    description=(
                        "Checks analytical ideal-binary vapor fraction, every "
                        "component balance, and the complete enthalpy ledger."
                    ),
                    status="implemented",
                    command_or_path="tests/test_flash_units.py",
                    tolerance="material and energy residual < 1e-12",
                ),
                ValidationEvidence(
                    evidence_id="tp-flash-gamma-phi-hooks",
                    evidence_type="unit_test",
                    description=(
                        "Exercises nonideal activity coefficients, vapor "
                        "fugacity coefficients, liquid reference factors, "
                        "Poynting factors, and fixed-point convergence."
                    ),
                    status="implemented",
                    command_or_path="tests/test_flash_units.py",
                    tolerance="material residual < 1e-10",
                ),
                ValidationEvidence(
                    evidence_id="thermo-ideal-tp-flash-comparison",
                    evidence_type="optional_reference_test",
                    description=(
                        "Compares the shared ideal K-value/Rachford-Rice phase "
                        "split against thermo's fixed-TP flash package."
                    ),
                    status="implemented",
                    reference_backend="thermo",
                    command_or_path=("tests/reference/test_optional_reference_backends.py"),
                    tolerance="vapor fraction and phase compositions <= 1e-8",
                ),
            ),
            model_limit_notes=(
                "Reference validation denotes an auditable benchmark unit, "
                "not a general EOS/GE flash package.",
                "Temperature-dependent enthalpy integration, phase stability, "
                "and automatic property-database selection remain external.",
            ),
            intended_use=(
                "Benchmark evaporation and flash scenarios that need visible "
                "material and heat-duty closure.",
                "Controlled nonideal VLE studies with caller-supplied property and fugacity data.",
            ),
        ),
    )


__all__ = ["flash_unit_model_cards"]
