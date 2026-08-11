"""Model card for deterministic electrochemical setpoint controllers."""

from __future__ import annotations

from chemworld.physchem.maturity import MaturityLevel, ModelCard, ValidationEvidence


def electrochem_control_model_cards() -> tuple[ModelCard, ...]:
    return (
        ModelCard(
            model_id="electrochemical_setpoint_recipe_controller_v1",
            module_id="electrochemistry",
            title="Replayable Potentiostatic And Galvanostatic Setpoint Controller",
            maturity=MaturityLevel.REFERENCE_VALIDATED,
            summary=(
                "Versioned potentiostatic/galvanostatic ramp and hold recipes "
                "with range/slew clipping, sampled traces, operation logs, and "
                "cryptographic replay contracts."
            ),
            equations=(
                "range target = clip(requested target, minimum, maximum)",
                "ramp endpoint = start + clip(target-start, -slew*t, +slew*t)",
                "ramp trace is linear between start and applied endpoint",
                "recipe hash = SHA256(canonical recipe + limits + initial state)",
                "execution hash = SHA256(canonical logs + trace + final state)",
            ),
            assumptions=(
                "The controller generates deterministic setpoints; electrochemical "
                "plant response is evaluated by separate kinetics/transport models.",
                "Ramp segments obey range and slew limits; hold segments are "
                "explicit setpoint steps and flag excessive sample-to-sample slew.",
                "Potential and current controller states are retained separately "
                "when a recipe switches mode.",
                "Canonical JSON uses sorted keys, compact separators, and no NaN.",
            ),
            validity_limits=(
                "Recipes support ramp and hold profiles only.",
                "Sampling is deterministic and includes both segment endpoints; "
                "mode-switch boundaries can have duplicate event times.",
                "PID dynamics, anti-windup, measurement filtering, and hardware "
                "latency are outside this setpoint engine.",
            ),
            failure_modes=(
                "Invalid ranges, slew limits, durations, schemas, duplicate ids, "
                "and nonfinite setpoints fail early.",
                "Range/slew clipping is logged rather than silently applied.",
                "Changed recipe, limits, initial state, logs, or trace causes replay mismatch.",
            ),
            units={
                "potential/current": "V; A",
                "potential/current slew": "V/s; A/s",
                "duration/sample time": "s",
                "recipe/execution hash": "64-character lowercase SHA-256 hex",
            },
            reference_reading=(
                "Potentiostatic and galvanostatic controller mode conventions",
                "Ramp/hold electrochemical experiment recipe and operation-log conventions",
                "Deterministic event-sourced replay and canonical artifact hashing practices",
            ),
            validation_evidence=(
                ValidationEvidence(
                    evidence_id="electrochem-ramp-hold-clipping-trace",
                    evidence_type="analytical_test",
                    description=(
                        "Checks potential/current range and slew clipping, linear "
                        "ramps, constant holds, mode switching, and step warnings."
                    ),
                    status="implemented",
                    command_or_path="tests/test_electrochem_control.py",
                    tolerance="pytest.approx setpoints and exact log flags",
                ),
                ValidationEvidence(
                    evidence_id="electrochem-controller-replay-hashes",
                    evidence_type="unit_test",
                    description=(
                        "Checks 64-hex recipe/execution hashes, exact deterministic "
                        "replay, and rejection after recipe mutation."
                    ),
                    status="implemented",
                    command_or_path="tests/test_electrochem_control.py",
                    tolerance="exact serialized execution equality",
                ),
            ),
            model_limit_notes=(
                "Reference validation applies to the reproducible control "
                "contract, not closed-loop hardware-control performance.",
                "Double-layer/plant response, PID tuning, noisy feedback, and "
                "instrument latency are separate concerns.",
            ),
            intended_use=(
                "Replayable electrochemical benchmark action recipes.",
                "Agent planning over potential/current ramps, holds, clipping, "
                "mode switches, and trace auditability.",
            ),
        ),
    )


__all__ = ["electrochem_control_model_cards"]
