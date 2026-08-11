"""Model card for Randles double-layer transients."""

from __future__ import annotations

from chemworld.physchem.maturity import MaturityLevel, ModelCard, ValidationEvidence


def electrochem_double_layer_model_cards() -> tuple[ModelCard, ...]:
    return (
        ModelCard(
            model_id="randles_double_layer_transient_v1",
            module_id="electrochemistry",
            title="Randles Double-Layer Capacitive Current Transient",
            maturity=MaturityLevel.PROFESSIONAL_CANDIDATE,
            summary=(
                "Analytical potential-step and current-step transients for a "
                "series resistance feeding a parallel double-layer capacitance "
                "and charge-transfer resistance, with current-component traces."
            ),
            equations=(
                "C_dl,total = C_dl,area A",
                "tau_E = (R_s || R_ct) C_dl; tau_I = R_ct C_dl",
                "potential step: i_C = DeltaE/R_s exp(-t/tau_E)",
                "potential step: i_F = DeltaE/(R_s+R_ct)[1-exp(-t/tau_E)]",
                "current step: i_C = I exp(-t/tau_I); i_F = I[1-exp(-t/tau_I)]",
                "Q_total = Q_F + Q_C",
            ),
            assumptions=(
                "R_s, R_ct, and double-layer capacitance are linear and constant.",
                "The potential/current command is an ideal instantaneous step.",
                "Faradaic current is the linear charge-transfer-resistance branch.",
                "No diffusion impedance, constant-phase element, or distributed porosity.",
            ),
            validity_limits=(
                "Positive series resistance, charge-transfer resistance, area, "
                "capacitance density, duration, and sample interval are required.",
                "The model describes small-signal/local linear RC behavior.",
                "Nonlinear Butler-Volmer and mass-transfer response must be "
                "coupled through separate model slices.",
            ),
            failure_modes=(
                "Nonphysical RC parameters and nonfinite commands fail early.",
                "Traces shorter than five time constants are flagged as incomplete.",
                "Startup current dominated by double-layer charging is an "
                "explicit artifact warning.",
            ),
            units={
                "capacitance density/total capacitance": "F/m^2; F",
                "resistance": "ohm",
                "time/time constant": "s",
                "potential/current": "V; A",
                "charge": "C",
            },
            reference_reading=(
                "Randles equivalent-circuit conventions for solution resistance, "
                "double-layer capacitance, and charge-transfer resistance",
                "Analytical first-order RC potential-step and current-step response",
                "Chronoamperometric startup-current separation into capacitive "
                "and Faradaic contributions",
            ),
            validation_evidence=(
                ValidationEvidence(
                    evidence_id="randles-potential-step-current-limits",
                    evidence_type="analytical_test",
                    description=(
                        "Checks time constant, initial DeltaE/Rs current, final "
                        "DeltaE/(Rs+Rct) current, and exponential component traces."
                    ),
                    status="implemented",
                    command_or_path="tests/test_electrochem_double_layer.py",
                    tolerance="pytest.approx analytical RC response",
                ),
                ValidationEvidence(
                    evidence_id="randles-current-step-charge-ledger",
                    evidence_type="analytical_test",
                    description=(
                        "Checks constant total current, complementary capacitive/"
                        "Faradaic currents, integrated charges, observation arrays, "
                        "and startup/incomplete-trace warnings."
                    ),
                    status="implemented",
                    command_or_path="tests/test_electrochem_double_layer.py",
                    tolerance="charge residual <= 1e-15 C",
                ),
                ValidationEvidence(
                    evidence_id="randles-runtime-electrochemistry-coupling",
                    evidence_type="runtime_integration_test",
                    description=(
                        "Exercises shared runtime integration with reaction kinetics, "
                        "diffusion transport, aqueous equilibrium, and the Randles "
                        "branch; verifies charge, material, and energy conservation "
                        "closure, runtime provenance diagnostics, and fail-closed "
                        "rollback at invalid domain limits."
                    ),
                    status="implemented",
                    command_or_path="tests/test_electrochem_equilibrium_coupling.py",
                    tolerance=(
                        "charge residual < 1e-9 C; material residual < 1e-12 mol; "
                        "energy residual < 1e-8 J"
                    ),
                ),
            ),
            model_limit_notes=(
                "Professional-candidate denotes a correct compact RC transient, "
                "not a full impedance or porous-electrode model.",
                "Warburg diffusion, CPE behavior, nonlinear kinetics, adsorption, "
                "and electrode aging are outside scope.",
            ),
            intended_use=(
                "Startup-artifact-aware electrochemical current observations.",
                "Agent reasoning over non-Faradaic charge, time constants, and "
                "when current becomes predominantly Faradaic.",
            ),
        ),
    )


__all__ = ["electrochem_double_layer_model_cards"]
