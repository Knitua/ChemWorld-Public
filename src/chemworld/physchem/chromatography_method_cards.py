"""Model card for empirical chromatography method sensitivity."""

from __future__ import annotations

from chemworld.physchem.maturity import MaturityLevel, ModelCard, ValidationEvidence


def chromatography_method_model_cards() -> tuple[ModelCard, ...]:
    return (
        ModelCard(
            model_id="empirical_chromatography_method_sensitivity_v1",
            module_id="spectroscopy_instruments",
            title="Empirical HPLC/GC Method Sensitivity And Detector Calibration",
            maturity=MaturityLevel.REFERENCE_VALIDATED,
            summary=(
                "Provenance-tagged analyte method cards for HPLC mobile-phase/"
                "temperature sensitivity, GC van't Hoff retention, logarithmic "
                "retention indices, detector calibration, and peak asymmetry."
            ),
            equations=(
                "HPLC: log10(k) = log10(k_ref) - S_phi(phi-phi_ref) + S_T(T-T_ref)",
                "GC: ln(k/k_ref) = -DeltaH_ret/R (1/T - 1/T_ref)",
                "t_R = t_M(1 + k)",
                "w_b = 4 t_R / sqrt(N)",
                "I = 100[n + (N-n)(ln t'_R - ln t'_n)/(ln t'_N - ln t'_n)]",
                "detector response = intercept + slope concentration",
                "LOD = 3.3 sigma/slope; LOQ = 10 sigma/slope",
            ),
            assumptions=(
                "Method sensitivities are empirical local coefficients tied to "
                "analyte, column/method, and provenance.",
                "HPLC uses one scalar organic mobile-phase fraction and a local "
                "temperature slope; gradient dwell-volume dynamics are absent.",
                "GC uses a local signed retention enthalpy at fixed carrier-flow "
                "and column conditions.",
                "Detector calibration is linear over the declared standards.",
                "Peak asymmetry is classified from a supplied tailing factor.",
                "Plate count is a declared synthetic method parameter, not fitted column data.",
            ),
            validity_limits=(
                "HPLC mobile-phase fraction is restricted to [0, 1].",
                "GC retention index requires an unknown adjusted retention time "
                "strictly bracketed by two n-alkane anchors.",
                "At least three concentration-response standards are required.",
                "The model does not extrapolate a global retention database.",
                "No claim is made that the synthetic trace predicts a real sample or column.",
            ),
            failure_modes=(
                "Instrument/method mismatches and invalid fractions fail early.",
                "Unbracketed retention indices and nonpositive fitted detector "
                "slopes fail rather than returning clipped estimates.",
                "Weak/strong retention and asymmetric peaks produce explicit warnings.",
            ),
            units={
                "temperature/temperature slope": "K; log10(k)/K",
                "time": "min",
                "retention factor/mobile fraction": "dimensionless",
                "retention enthalpy": "J/mol",
                "retention index/tailing factor": "dimensionless",
                "detector slope/intercept": "response/concentration; response",
                "LOD/LOQ": "same concentration unit as standards",
            },
            reference_reading=(
                "van Deemter/retention-factor and Snyder solvent-strength "
                "conventions for empirical liquid chromatography method development",
                "Kovats and linear/log adjusted-retention index interpolation "
                "conventions for gas chromatography",
                "ICH-style linear detector calibration, residual uncertainty, "
                "LOD, and LOQ reporting conventions",
            ),
            validation_evidence=(
                ValidationEvidence(
                    evidence_id="hplc-gc-method-sensitivity",
                    evidence_type="analytical_test",
                    description=(
                        "Checks reference retention, stronger-mobile-phase and "
                        "higher-temperature shifts, GC van't Hoff direction, "
                        "and midpoint logarithmic retention index."
                    ),
                    status="implemented",
                    command_or_path="tests/test_chromatography_methods.py",
                    tolerance="pytest.approx analytical examples",
                ),
                ValidationEvidence(
                    evidence_id="detector-calibration-and-asymmetry-flags",
                    evidence_type="unit_test",
                    description=(
                        "Checks fitted slope/intercept/R2/LOD/LOQ, forward/"
                        "inverse response, and fronting/tailing severity classes."
                    ),
                    status="implemented",
                    command_or_path="tests/test_chromatography_methods.py",
                    tolerance="R2 > 0.999 and exact shape flags",
                ),
            ),
            model_limit_notes=(
                "Reference validation covers the bounded synthetic observation contract; "
                "professional maturity requires runtime diagnostics and provenance.",
                "Gradient profiles, column aging, mass overload, adsorption "
                "isotherms, and full asymmetric peak synthesis remain external.",
            ),
            intended_use=(
                "Method-selection and calibration benchmark tasks.",
                "Agent reasoning over temperature, solvent strength, runtime, "
                "response uncertainty, and asymmetric-peak warnings.",
            ),
        ),
    )


__all__ = ["chromatography_method_model_cards"]
