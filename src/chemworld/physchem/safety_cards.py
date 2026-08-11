"""Model cards for process safety envelopes."""

from __future__ import annotations

from chemworld.physchem.maturity import MaturityLevel, ModelCard, ValidationEvidence


def safety_envelope_model_cards() -> tuple[ModelCard, ...]:
    return (
        ModelCard(
            model_id="pressure_temperature_runaway_safety_envelope_v1",
            module_id="safety_constraints",
            title="Pressure, Temperature, Relief, And Runaway Safety Envelope",
            maturity=MaturityLevel.REFERENCE_VALIDATED,
            summary=(
                "Auditable process safety assessment combining current and "
                "projected pressure/temperature limits, MTSR, Arrhenius heat "
                "sensitivity, relief load, machine-readable flags, and cost."
            ),
            equations=(
                "dT/dt = (Q_generation - Q_removal)/C_process",
                "dQ_generation/dT = Q_generation E_a/(R T^2)",
                "DeltaT_ad = Q_remaining/C_process; MTSR = T + DeltaT_ad",
                "slope margin = UA_removal - dQ_generation/dT",
                "relief load ratio = vapor generation / relief capacity",
                "safety cost = w_risk risk + relief cost + shutdown cost",
            ),
            assumptions=(
                "The heat-generation slope is a local Arrhenius approximation.",
                "Heat removal is represented by its current duty and local temperature slope.",
                "Remaining exotherm is converted to an adiabatic temperature "
                "rise with constant process heat capacity.",
                "Relief capacity and vapor generation use a common mass basis.",
                "Risk weights and event costs are explicit envelope-card inputs.",
            ),
            validity_limits=(
                "This is a screening and benchmark envelope, not a DIERS "
                "relief-device sizing calculation.",
                "Pressure projection assumes a locally constant pressure rate.",
                "MTSR does not include heat-capacity or reaction-enthalpy "
                "variation with conversion and temperature.",
                "Envelope thresholds and relief capacity require equipment- "
                "and scenario-specific provenance.",
            ),
            failure_modes=(
                "Misordered warning, relief, and maximum limits fail early.",
                "Nonfinite or nonphysical heat, capacity, rate, and relief "
                "inputs fail before assessment.",
                "MAWP breach or insufficient relief capacity sets emergency "
                "shutdown status rather than only increasing a scalar score.",
            ),
            units={
                "temperature/temperature rate": "K; K/s",
                "pressure/pressure rate": "Pa; Pa/s",
                "heat generation/removal": "W",
                "heat slope/process heat capacity": "W/K; J/K",
                "remaining exotherm": "J",
                "activation energy": "J/mol",
                "vapor/relief mass rate": "kg/s",
                "risk/severity/load ratio": "dimensionless",
                "incremental safety cost": "declared benchmark cost units",
            },
            reference_reading=(
                "Semenov thermal-explosion stability criterion: comparison of "
                "heat-generation and heat-removal slopes",
                "MTSR and adiabatic temperature-rise screening conventions in "
                "reaction calorimetry and process safety",
                "DIERS-style distinction between relief load and rated relief "
                "capacity; this model does not perform device sizing",
            ),
            validation_evidence=(
                ValidationEvidence(
                    evidence_id="arrhenius-heat-slope-and-projection",
                    evidence_type="analytical_test",
                    description=(
                        "Checks the analytic Arrhenius derivative, net-heat "
                        "temperature rate, MTSR, and time-to-limit projections."
                    ),
                    status="implemented",
                    command_or_path="tests/test_safety_envelope.py",
                    tolerance="pytest.approx analytical formulas",
                ),
                ValidationEvidence(
                    evidence_id="relief-emergency-and-cost-integration",
                    evidence_type="unit_test",
                    description=(
                        "Checks normal, warning, relief, MAWP, insufficient "
                        "capacity, emergency status, flags, risk, and exact "
                        "incremental safety-cost composition."
                    ),
                    status="implemented",
                    command_or_path="tests/test_safety_envelope.py",
                    tolerance="exact flags and pytest.approx cost ledger",
                ),
            ),
            model_limit_notes=(
                "Reference validation means the envelope is structured and "
                "auditable, not that it substitutes for a process hazard review.",
                "Two-phase relief hydrodynamics, vent-network backpressure, "
                "decomposition kinetics, and validated plant safeguards are absent.",
            ),
            intended_use=(
                "Safety-constrained benchmark tasks and interpretable failure flags.",
                "Agent planning over conversion, cooling, pressure, relief, and "
                "incremental safety cost.",
            ),
        ),
    )


__all__ = ["safety_envelope_model_cards"]
