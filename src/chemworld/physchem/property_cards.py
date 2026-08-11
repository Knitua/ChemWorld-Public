"""Property-correlation model cards for ChemWorld."""

from __future__ import annotations

from chemworld.physchem.maturity import MaturityLevel, ModelCard, ValidationEvidence

_HEAT_ENTHALPY_REFERENCE_READING = (
    "reference_repos/chemicals/chemicals/dippr.py: EQ100 value and "
    "temperature integral",
    "reference_repos/chemicals/chemicals/heat_capacity.py: gas/liquid/solid "
    "heat-capacity method families and integral APIs",
    "reference_repos/chemicals/chemicals/phase_change.py: Watson latent-heat "
    "temperature correction",
    "reference_repos/thermo/thermo/chemical.py: phase-reference enthalpy "
    "paths across melting and boiling transitions",
)

_VOLUME_REFERENCE_READING = (
    "reference_repos/chemicals/chemicals/volume.py: Rackett liquid molar "
    "volume, Amgat liquid-mixture rule, ideal_gas, and CRC virial data notes",
    "reference_repos/chemicals/chemicals/virial.py: second-virial gas-volume "
    "families and mixture hooks",
    "reference_repos/thermo/thermo/volume.py: VolumeLiquid, VolumeGas, and "
    "VolumeLiquidMixture method organization and validity policy",
)

_TRANSPORT_REFERENCE_READING = (
    "reference_repos/chemicals/chemicals/viscosity.py: Andrade-like pure "
    "viscosity families and Wilke gas-mixture viscosity rule",
    "reference_repos/chemicals/chemicals/thermal_conductivity.py: DIPPR9B gas "
    "conductivity and DIPPR9H/DIPPR9I liquid-mixture conductivity rules",
    "reference_repos/thermo/thermo/viscosity.py and thermal_conductivity.py: "
    "method-governance organization for pure and mixture transport properties",
    "reference_repos/idaes-pse/.../viscosity_wilke.py: process-model Wilke "
    "callback pattern for gas-mixture viscosity",
    "reference_repos/idaes-pse/.../gas_phase_thermo.py: Fuller-style gas "
    "diffusivity scaling and mixture-diffusivity closure",
)

def property_correlation_model_cards() -> tuple[ModelCard, ...]:
    """Return model cards for generic property-correlation families."""

    return (
        ModelCard(
            model_id="vapor_pressure_correlation_families",
            module_id="properties",
            title="Vapor-Pressure Correlation Families",
            maturity=MaturityLevel.REFERENCE_VALIDATED,
            summary=(
                "Formula-level vapor and sublimation pressure evaluators with "
                "explicit validity ranges, analytic temperature derivatives, "
                "and JSON-friendly reports."
            ),
            equations=(
                "Antoine: log_base(P) = A - B/(T + C)",
                "Wagner original 3,6 form: ln(P/Pc) = "
                "(a*tau + b*tau**1.5 + c*tau**3 + d*tau**6)/Tr",
                "DIPPR101: P = exp(A + B/T + C*ln(T) + D*T**E)",
                "dP/dT is analytic for Antoine, Wagner, and DIPPR101 reports.",
            ),
            assumptions=(
                "Coefficient units must match each PropertyCorrelation input "
                "and output unit declaration.",
                "Validity ranges are treated as benchmark contracts; callers "
                "choose warn, raise, or ignore policy.",
                "Sublimation pressure uses the same formula families when a "
                "caller supplies sublimation-pressure coefficients.",
            ),
            validity_limits=(
                "No automatic method ranking beyond the caller-provided "
                "correlation order in ComponentPropertyPackage.",
                "No data-table vendoring; only explicitly curated coefficients "
                "are shipped.",
                "Critical-region behavior is limited to declared correlation "
                "validity bounds.",
            ),
            failure_modes=(
                "Unsupported equations fail before derivative evaluation.",
                "Antoine singularities fail when T + C is nonpositive.",
                "Wagner reports fail at or above the declared critical temperature.",
                "Out-of-range calls can hard-fail with validity_policy='raise'.",
            ),
            units={
                "temperature": "K or declared temperature unit",
                "pressure": "Pa or declared pressure unit",
                "dP_dT": "declared_pressure_unit/K",
                "dlnP_dT": "1/K",
            },
            reference_reading=(
                "reference_repos/chemicals/chemicals/vapor_pressure.py: "
                "Antoine, Wagner, dWagner_dT, vapor-pressure data families",
                "reference_repos/chemicals/chemicals/dippr.py: EQ101 and "
                "order=1 derivative",
                "reference_repos/thermo/thermo/vapor_pressure.py: "
                "VaporPressure method ranking, validity limits, and derivative API",
            ),
            validation_evidence=(
                ValidationEvidence(
                    evidence_id="antoine-vapor-pressure-derivative-test",
                    evidence_type="unit_test",
                    description=(
                        "Checks Antoine pressure and analytic derivative "
                        "against central finite differences."
                    ),
                    status="implemented",
                    command_or_path="tests/test_physchem_properties.py",
                    tolerance="rtol=1e-5",
                ),
                ValidationEvidence(
                    evidence_id="dippr101-vapor-pressure-derivative-test",
                    evidence_type="unit_test",
                    description=(
                        "Checks DIPPR101 analytic dP/dT against central finite "
                        "differences for curated compounds."
                    ),
                    status="implemented",
                    command_or_path="tests/test_physchem_properties.py",
                    tolerance="rtol=1e-5",
                ),
            ),
            model_limit_notes=(
                "This is a compact formula-family implementation, not a "
                "replacement for chemicals/thermo data coverage or EOS-based "
                "critical-region saturation solvers.",
            ),
            intended_use=(
                "Flash, distillation, volatility-risk, and safety-envelope "
                "tasks requiring auditable vapor-pressure values and slopes.",
                "Benchmark datasets that need replayable property reports with "
                "validity status.",
            ),
        ),
        ModelCard(
            model_id="pure_fluid_saturation_solver",
            module_id="properties",
            title="Pure-Fluid Saturation Solver",
            maturity=MaturityLevel.REFERENCE_VALIDATED,
            summary=(
                "Auditable pure-fluid saturation reports built on explicit "
                "vapor-pressure correlations, analytic pressure slopes, "
                "bracketed temperature inversion, and critical-region guards."
            ),
            equations=(
                "Forward saturation: P_sat = vapor_pressure_report(T).",
                "Inverse saturation: solve ln(P_sat(T)/P_target) = 0.",
                "Temperature inversion uses bracketed bisection on the "
                "log-pressure residual.",
                "Critical guards require T < Tc and P < Pc when critical "
                "properties are supplied.",
            ),
            assumptions=(
                "The vapor-pressure correlation remains the source of the "
                "saturation curve; the solver does not infer hidden data.",
                "Temperature brackets come from declared validity ranges unless "
                "the caller supplies an explicit bracket.",
                "Critical warnings are metadata for benchmark agents, not "
                "high-accuracy critical-region thermodynamics.",
            ),
            validity_limits=(
                "Pure-fluid only; mixture bubble/dew and azeotrope behavior are "
                "handled by later flash tasks.",
                "No EOS phase-envelope tracing or superancillary equations are "
                "implemented in this slice.",
                "A non-bracketing target pressure hard-fails instead of "
                "extrapolating silently.",
            ),
            failure_modes=(
                "Nonpositive pressure or temperature fails.",
                "T >= Tc or P >= Pc fails when critical properties are supplied.",
                "No bracketing sign change fails with residual diagnostics.",
                "Unsupported vapor-pressure equations fail through the lower "
                "property-correlation layer.",
            ),
            units={
                "temperature": "K",
                "pressure": "Pa",
                "log_pressure_residual": "dimensionless",
            },
            reference_reading=(
                "reference_repos/thermo/thermo/vapor_pressure.py: "
                "VaporPressure method governance and validity limits",
                "reference_repos/coolprop/Web/coolprop/HighLevelAPI.rst: "
                "saturation inputs with vapor quality and critical-region "
                "warnings",
                "reference_repos/phasepy/phasepy/mixtures.py: Psat/Tsat "
                "inverse API shape for Antoine-like correlations",
            ),
            validation_evidence=(
                ValidationEvidence(
                    evidence_id="pure-saturation-temperature-inversion-test",
                    evidence_type="unit_test",
                    description=(
                        "Checks water Antoine Psat/Tsat closure and normal "
                        "boiling-point inversion with residual diagnostics."
                    ),
                    status="implemented",
                    command_or_path="tests/test_physchem_properties.py",
                    tolerance="relative temperature tolerance 5e-4",
                ),
                ValidationEvidence(
                    evidence_id="pure-saturation-critical-guard-test",
                    evidence_type="unit_test",
                    description=(
                        "Checks near-critical warnings, critical hard-fails, "
                        "and non-bracketing pressure failures."
                    ),
                    status="implemented",
                    command_or_path="tests/test_physchem_properties.py",
                    tolerance="guardrail behavior",
                ),
            ),
            model_limit_notes=(
                "This is a reference-validated numerical contract for "
                "benchmark saturation calls, not a replacement for CoolProp "
                "or full EOS phase-envelope tracing.",
            ),
            intended_use=(
                "Flash, distillation, vapor-loss, pressure-risk, and scenario "
                "generation tasks needing replayable pure-fluid saturation "
                "points.",
                "Dataset exports that need explicit residuals, brackets, and "
                "critical warning metadata.",
            ),
        ),
        ModelCard(
            model_id="phase_heat_capacity_enthalpy_package",
            module_id="properties",
            title="Phase-Aware Heat Capacity And Enthalpy Package",
            maturity=MaturityLevel.REFERENCE_VALIDATED,
            summary=(
                "Phase-tagged molar heat-capacity evaluation, analytic "
                "sensible-enthalpy integrals, signed latent-heat transitions, "
                "and mixture enthalpy ledgers for reactor and separation duties."
            ),
            equations=(
                "DIPPR100-style Cp polynomial: Cp = a + bT + cT^2 + dT^3 + eT^4.",
                "Sensible enthalpy: Delta H = integral Cp(T) dT along one phase.",
                "Watson latent heat: Hvap(T) = Hvap_ref*((1-Tr)/(1-Tr_ref))^n.",
                "Phase paths sum sensible segments plus signed latent heats.",
                "Mixture duty: Delta H_mix = sum_i n_i Delta H_i.",
            ),
            assumptions=(
                "Heat-capacity correlations are molar and declare their phase "
                "in metadata when a phase-specific API is used.",
                "Reference-state temperature is explicit in every report; no "
                "global hidden enthalpy zero is assumed.",
                "Transitions are caller-declared and traversed by phase labels "
                "rather than inferred from hidden data tables.",
            ),
            validity_limits=(
                "Only analytic cp_polynomial integrals are implemented in this "
                "slice; tabular and Zabransky/Lastovka families remain future "
                "deepening tasks.",
                "Latent heat supports the existing Watson and constant "
                "phase-change correlations with caller-supplied coefficients.",
                "No EOS departure enthalpy, pressure correction, or broad "
                "component database is included here.",
            ),
            failure_modes=(
                "Unsupported Cp equations fail before integration.",
                "Missing phase Cp, invalid phase labels, and disconnected phase "
                "paths fail explicitly.",
                "Negative heat capacity over sampled integration intervals "
                "hard-fails instead of being clipped.",
                "Latent heat direction is signed; invalid transition direction "
                "raises a validation error.",
            ),
            units={
                "temperature": "K",
                "heat_capacity": "J/(mol*K)",
                "molar_enthalpy": "J/mol",
                "mixture_enthalpy": "J",
            },
            reference_reading=_HEAT_ENTHALPY_REFERENCE_READING,
            validation_evidence=(
                ValidationEvidence(
                    evidence_id="phase-cp-integral-regression-test",
                    evidence_type="unit_test",
                    description=(
                        "Checks gas, liquid, and solid Cp polynomial integrals "
                        "and reference-state zero behavior."
                    ),
                    status="implemented",
                    command_or_path="tests/test_physchem_properties.py",
                    tolerance="rtol=1e-12",
                ),
                ValidationEvidence(
                    evidence_id="phase-transition-ledger-test",
                    evidence_type="unit_test",
                    description=(
                        "Checks signed vaporization/condensation latent heat "
                        "and mole-weighted mixture enthalpy ledger closure."
                    ),
                    status="implemented",
                    command_or_path="tests/test_physchem_properties.py",
                    tolerance="rtol=1e-12",
                ),
            ),
            model_limit_notes=(
                "This closes a path/ledger slice needed by ChemWorld reactor "
                "and flash duties. It is not chemicals/thermo data coverage, "
                "CoolProp-level reference-state thermodynamics, or an EOS "
                "departure-property package.",
            ),
            intended_use=(
                "Dynamic reactor heat-duty ledgers and flash/distillation "
                "energy-balance checks.",
                "Benchmark trajectories that need auditable sensible and "
                "latent heat contributions with provenance.",
            ),
        ),
        ModelCard(
            model_id="density_molar_volume_package",
            module_id="properties",
            title="Density And Molar-Volume Package",
            maturity=MaturityLevel.REFERENCE_VALIDATED,
            summary=(
                "Liquid Rackett molar volume, ideal-gas and second-virial gas "
                "volume reports, density/molar-volume conversion helpers, and "
                "Amgat-style mixture volume ledgers."
            ),
            equations=(
                "Rackett: Vm = R Tc/Pc * Zc**(1 + (1 - T/Tc)**(2/7)).",
                "Ideal gas: Vm = R T/P, Z = 1.",
                "CRC second virial polynomial: B = (a1 + t(a2 + t(a3 + "
                "t(a4 + a5 t))))*1e-6, t = 298.15/T - 1.",
                "Virial gas root: P Vm^2 - R T Vm - R T B = 0.",
                "Amgat mixture: Vm_mix = sum_i x_i Vm_i.",
            ),
            assumptions=(
                "Liquid Rackett reports are low-pressure saturated-liquid style "
                "estimates and require caller-supplied critical constants.",
                "Virial gas reports are intended for low to moderate density; "
                "compressibility status is reported from |B/Vm|.",
                "Mixture volume ledger assumes zero excess volume.",
            ),
            validity_limits=(
                "Rackett hard-fails at or above Tc and does not apply a "
                "compressed-liquid Tait correction.",
                "Only a CRC-style second-virial coefficient polynomial hook is "
                "implemented; broader Tsonopoulos/Pitzer families are future "
                "deepening work.",
                "No bulk component density database is vendored.",
            ),
            failure_modes=(
                "Nonpositive Tc, Pc, Zc, temperature, pressure, density, "
                "molecular weight, or molar volume raises ValueError.",
                "Virial roots fail when the quadratic has no positive gas "
                "molar-volume root.",
                "Mixture ledgers fail on fraction mismatch, missing component "
                "volume, or missing molecular weight.",
            ),
            units={
                "temperature": "K",
                "pressure": "Pa",
                "molar_volume": "m^3/mol",
                "density": "kg/m^3",
                "molecular_weight": "g/mol",
                "second_virial": "m^3/mol",
            },
            reference_reading=_VOLUME_REFERENCE_READING,
            validation_evidence=(
                ValidationEvidence(
                    evidence_id="rackett-liquid-volume-test",
                    evidence_type="unit_test",
                    description=(
                        "Checks Rackett liquid molar volume and density "
                        "conversion against a hand calculation."
                    ),
                    status="implemented",
                    command_or_path="tests/test_physchem_properties.py",
                    tolerance="rtol=1e-12",
                ),
                ValidationEvidence(
                    evidence_id="virial-gas-volume-root-test",
                    evidence_type="unit_test",
                    description=(
                        "Checks the second-virial gas-volume quadratic root, "
                        "compressibility factor, and warning status."
                    ),
                    status="implemented",
                    command_or_path="tests/test_physchem_properties.py",
                    tolerance="rtol=1e-12",
                ),
            ),
            model_limit_notes=(
                "This is a density/molar-volume ledger slice for ChemWorld "
                "tasks. It is not CoolProp density coverage, compressed-liquid "
                "Tait modeling, COSTALD mixture fitting, or a full virial "
                "correlation library.",
            ),
            intended_use=(
                "Flash, distillation, extraction, and safety tasks that need "
                "auditable volume/density values.",
                "Benchmark records that need compressibility status instead of "
                "unlabeled gas-density corrections.",
            ),
        ),
        ModelCard(
            model_id="transport_property_package",
            module_id="properties",
            title="Transport Property Package",
            maturity=MaturityLevel.REFERENCE_VALIDATED,
            summary=(
                "Pure-component viscosity and thermal-conductivity reports, "
                "Wilke gas-mixture viscosity ledgers, DIPPR9H liquid-mixture "
                "conductivity ledgers, Fuller-style gas diffusivity estimates, "
                "and thermal-diffusivity reports with explicit uncertainty and "
                "validity metadata."
            ),
            equations=(
                "Andrade/Arrhenius viscosity: mu = A exp(B/T).",
                "Sutherland gas viscosity: mu = mu_ref (T/T_ref)^1.5 "
                "(T_ref + S)/(T + S).",
                "Linear conductivity: k = k_ref(1 + alpha(T - T_ref)); "
                "polynomial conductivity is also supported.",
                "DIPPR9B gas conductivity from gas viscosity, Cv, molecular "
                "weight, molecule type, and critical temperature.",
                "Wilke gas mixture: mu_mix = sum_i y_i mu_i / sum_j y_j phi_ij.",
                "DIPPR9H liquid mixture: k_mix = (sum_i w_i/k_i^2)^-0.5.",
                "Fuller gas diffusivity scales as T^1.75/P and diffusion-volume "
                "groups; mixture effective diffusivity uses resistance summation.",
                "Thermal diffusivity: alpha = k/(rho Cp).",
            ),
            assumptions=(
                "Pure-property correlations use caller-supplied coefficients "
                "with declared units and validity ranges.",
                "Wilke and Fuller paths are low-pressure gas estimates; reported "
                "uncertainty metadata must remain visible to tasks and datasets.",
                "Liquid mixture conductivity uses the nonaqueous DIPPR9H rule "
                "unless a future task selects another ledger.",
            ),
            validity_limits=(
                "No broad viscosity, conductivity, or diffusion-volume database "
                "is vendored.",
                "No high-pressure gas viscosity correction, electrolyte "
                "transport, multicomponent Maxwell-Stefan solver, or "
                "temperature-dependent calibrated diffusion model is included.",
                "DIPPR9H warnings are emitted for broad use and when component "
                "conductivities differ by more than 2x.",
            ),
            failure_modes=(
                "Nonpositive temperature, pressure, viscosity, conductivity, "
                "diffusivity, density, heat capacity, molecular weight, or "
                "diffusion volume raises ValueError.",
                "Composition/key mismatches fail explicitly before mixture "
                "ledger construction.",
                "Unsupported molecule types or missing critical temperature for "
                "linear DIPPR9B gas conductivity fail explicitly.",
            ),
            units={
                "temperature": "K",
                "pressure": "Pa",
                "dynamic_viscosity": "Pa*s",
                "thermal_conductivity": "W/(m*K)",
                "diffusivity": "m^2/s",
                "molecular_weight": "g/mol",
            },
            reference_reading=_TRANSPORT_REFERENCE_READING,
            validation_evidence=(
                ValidationEvidence(
                    evidence_id="transport-viscosity-conductivity-report-test",
                    evidence_type="unit_test",
                    description=(
                        "Checks Andrade/Sutherland reports, conductivity "
                        "validity, and unit conversion."
                    ),
                    status="implemented",
                    command_or_path="tests/test_physchem_properties.py",
                    tolerance="rtol=1e-12",
                ),
                ValidationEvidence(
                    evidence_id="transport-mixture-diffusivity-ledger-test",
                    evidence_type="unit_test",
                    description=(
                        "Checks Wilke gas viscosity, DIPPR9H liquid "
                        "conductivity, Fuller binary gas diffusivity, and "
                        "mixture effective diffusivity ledgers."
                    ),
                    status="implemented",
                    command_or_path="tests/test_physchem_properties.py",
                    tolerance="rtol=1e-12",
                ),
            ),
            model_limit_notes=(
                "This is a compact transport-property reporting and ledger "
                "slice for ChemWorld tasks. It is not a replacement for "
                "chemicals/thermo/CoolProp transport coverage or a full "
                "Maxwell-Stefan transport backend.",
            ),
            intended_use=(
                "Heat-transfer, reactor, distillation, separation, and "
                "instrument tasks that need explicit transport properties.",
                "Benchmark logs that must expose uncertainty and method family "
                "rather than silently using constants.",
            ),
        ),
    )




__all__ = [
    "_HEAT_ENTHALPY_REFERENCE_READING",
    "_TRANSPORT_REFERENCE_READING",
    "_VOLUME_REFERENCE_READING",
    "property_correlation_model_cards",
]
