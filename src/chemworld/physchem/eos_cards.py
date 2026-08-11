"""Equation-of-state model cards for ChemWorld."""

from __future__ import annotations

from chemworld.physchem.maturity import MaturityLevel, ModelCard, ValidationEvidence


def eos_model_cards() -> tuple[ModelCard, ...]:
    return (
        ModelCard(
            model_id="cubic_eos_pr_srk_residuals",
            module_id="eos",
            title="Peng-Robinson/SRK Cubic EOS Fugacity And Residual Properties",
            maturity=MaturityLevel.REFERENCE_VALIDATED,
            summary=(
                "Compact PR/SRK cubic-EOS slice with one-fluid mixing, explicit "
                "root selection, fugacity coefficients, and molar residual "
                "enthalpy/entropy/Gibbs properties."
            ),
            equations=(
                "a_i(T)=Omega_a R^2 Tc_i^2/Pc_i alpha_i(T)",
                "b_i=Omega_b R Tc_i/Pc_i",
                "a_mix=sum_i sum_j x_i x_j sqrt(a_i a_j)(1-k_ij)",
                "b_mix=sum_i x_i b_i",
                "PR: H^R=RT(Z-1)+(T da/dT-a)/(2 sqrt(2) b) ln((Z+(1+sqrt(2))B)/(Z+(1-sqrt(2))B))",
                "SRK: H^R=RT(Z-1)+(T da/dT-a)/b ln((Z+B)/Z)",
                "S^R=R ln(Z-B)+(da/dT/c) ln(argument), with c=2 sqrt(2) b for PR and b for SRK",
            ),
            assumptions=(
                "Classical quadratic mixing rules with optional symmetric k_ij.",
                "Pure-component alpha functions use the standard PR and SRK acentric-factor forms.",
                "Residual properties are molar mixture departures from ideal gas "
                "at the same T/P/composition.",
            ),
            validity_limits=(
                "Requires positive critical temperature, critical pressure, "
                "pressure, and temperature.",
                "Root selection is explicit but no phase-stability or "
                "phase-envelope solve is claimed.",
                "Near-critical and highly associating/polar fluids require "
                "stronger EOS or fitted parameters.",
            ),
            failure_modes=(
                "No admissible real Z root raises ValueError.",
                "Invalid composition ids, negative composition entries, or "
                "nonpositive log arguments raise ValueError.",
                "Missing binary parameters default to k_ij=0 and should be "
                "governed by scenario metadata.",
            ),
            units={
                "temperature": "K",
                "pressure": "Pa",
                "molar_volume": "m^3/mol",
                "residual_enthalpy": "J/mol",
                "residual_entropy": "J/(mol*K)",
                "fugacity_coefficient": "dimensionless",
            },
            reference_reading=(
                "reference_repos/thermo/thermo/eos.py "
                "main_derivatives_and_departures and PR/SRK classes",
                "reference_repos/phasepy/phasepy/cubic/cubicpure.py and "
                "cubicmix.py logfug/EntropyR/EnthalpyR APIs",
                "reference_repos/thermopack/addon/pycThermopack/thermopack/"
                "thermo.py residual enthalpy/entropy API",
                "reference_repos/teqp/teqp/__init__.py exposes fugacity and "
                "critical/VLE architecture hooks",
            ),
            validation_evidence=(
                ValidationEvidence(
                    evidence_id="default-eos-residual-tests",
                    evidence_type="unit_tests",
                    description=(
                        "Default tests cover low-pressure ideal-gas limits, explicit "
                        "root policy, Gibbs consistency with fugacity coefficients, "
                        "and positive PR/SRK mixture fugacity coefficients."
                    ),
                    status="passing",
                    command_or_path="python -m pytest tests/test_eos.py",
                    tolerance="relative tolerances documented in tests",
                ),
                ValidationEvidence(
                    evidence_id="optional-thermo-eos-reference",
                    evidence_type="optional_reference_backend",
                    description=(
                        "Optional checks compare selected pure-fluid PR/SRK vapor "
                        "root Z, phi, H_dep, and S_dep against thermo.eos when "
                        "CHEMWORLD_RUN_REFERENCE_TESTS=1."
                    ),
                    status="optional",
                    reference_backend="thermo",
                    command_or_path=(
                        "CHEMWORLD_RUN_REFERENCE_TESTS=1 python -m pytest "
                        "tests/reference/test_optional_reference_backends.py"
                    ),
                    tolerance="1e-6 relative for reference backend comparisons",
                ),
            ),
            intended_use=(
                "Benchmark dense-gas and vapor-loss calculations.",
                "Future flash, distillation, and reactor energy-balance modules "
                "that need compact residual properties.",
            ),
        ),
        ModelCard(
            model_id="cubic_eos_volume_translation_root_governance",
            module_id="eos",
            title="Volume-Translated Cubic EOS And Root Governance Diagnostics",
            maturity=MaturityLevel.REFERENCE_VALIDATED,
            summary=(
                "Peneloux-style volume-translation reporting and root-governance "
                "diagnostics layered on the compact PR/SRK cubic EOS. The slice "
                "keeps translation shifts, binary-interaction provenance, root "
                "selection evidence, and translated molar volumes explicit in "
                "JSON-friendly reports."
            ),
            equations=(
                "c_mix=sum_i x_i c_i",
                "V_translated=V_eos-c_mix",
                "Z_translated=P V_translated/(R T)=Z_eos-c_mix P/(R T)",
                "Translated cubic roots use C=c_mix P/(R T) and admissibility Z>B-C.",
                "Stable-root diagnostics rank roots by mixture residual Gibbs score.",
            ),
            assumptions=(
                "Translation parameters are supplied by the caller or scenario card.",
                "Binary interaction parameters are local model inputs and can be "
                "required to carry explicit provenance records.",
                "Root-governance reports expose evidence rather than hiding root "
                "selection inside a solver side effect.",
            ),
            validity_limits=(
                "Only PR and SRK cubic EOS families are supported.",
                "Volume translation is a compact Peneloux-style molar-volume "
                "correction, not a broad density database or critical-region model.",
                "Translated fugacity-composition derivatives, saturation curves, "
                "and full phase-envelope algorithms remain future slices.",
            ),
            failure_modes=(
                "Translated molar volume <= 0 raises ValueError.",
                "Unknown or duplicate volume-translation component records raise ValueError.",
                "Missing or mismatched binary-interaction provenance can be required "
                "to raise ValueError before evaluation.",
                "No admissible translated cubic root raises ValueError.",
            ),
            units={
                "temperature": "K",
                "pressure": "Pa",
                "volume_translation_shift": "m^3/mol",
                "molar_volume": "m^3/mol",
                "compressibility_factor": "dimensionless",
                "binary_interaction": "dimensionless",
            },
            reference_reading=(
                "reference_repos/phasepy/phasepy/cubic/vtcubicpure.py and "
                "vtcubicmix.py expose translated cubic roots with C=cP/RT.",
                "reference_repos/thermopack/src/volume_shift.f90 applies "
                "Peneloux volume shifts to Z and tracks component c_i values.",
                "reference_repos/thermopack/src/cubic.f90 documents root flags "
                "including smallest, largest, and minimum-Gibbs root selection.",
                "reference_repos/thermo/thermo/eos_mix_methods.py separates "
                "translated b0, b, and c terms in PR/SRK translated lnphi paths.",
            ),
            validation_evidence=(
                ValidationEvidence(
                    evidence_id="volume-translation-root-governance-tests",
                    evidence_type="unit_tests",
                    description=(
                        "Default EOS tests cover pure-liquid volume translation, "
                        "translated cubic roots, vapor-root warnings, stable-root "
                        "diagnostic ranking, binary-interaction provenance, and "
                        "negative translated-volume failures."
                    ),
                    status="passing",
                    command_or_path="python -m pytest tests/test_eos.py",
                    tolerance="analytical consistency and pytest.approx checks",
                ),
            ),
            model_limit_notes=(
                "This slice deliberately does not vendor reference-library data tables.",
                "The compact report keeps residual/fugacity conventions visible; "
                "full translated fugacity derivatives are left for a later flash slice.",
            ),
            intended_use=(
                "Dense-fluid volume diagnostics in flash, distillation, and "
                "generalization tasks.",
                "Auditable scenario manifests with binary-interaction and "
                "volume-shift provenance.",
            ),
        ),
    )




__all__ = [
    "eos_model_cards",
]
