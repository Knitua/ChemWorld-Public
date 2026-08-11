"""Model card for serializable equipment specifications."""

from __future__ import annotations

from chemworld.physchem.maturity import MaturityLevel, ModelCard, ValidationEvidence


def equipment_spec_model_cards() -> tuple[ModelCard, ...]:
    return (
        ModelCard(
            model_id="typed_equipment_card_constraints_v1",
            module_id="equipment",
            title="Typed Equipment Cards And Operating Constraints",
            maturity=MaturityLevel.LITE,
            summary=(
                "Versioned JSON equipment cards for vessels, pumps, mixers, "
                "condensers, heat exchangers, and columns with shared, "
                "machine-evaluable min/max operating constraints."
            ),
            equations=(
                "margin_max = limit - operating value",
                "margin_min = operating value - limit",
                "normalized margin = margin/max(abs(limit), epsilon)",
                "utilization_max = value/limit; utilization_min = limit/value",
                "feasible iff no hard constraint is violated",
            ),
            assumptions=(
                "Each field name includes its canonical unit suffix and each "
                "constraint also declares a human-readable unit.",
                "Factory functions define the standard constraint set for each "
                "supported equipment class.",
                "Warning constraints affect diagnostics but do not make an "
                "operating point infeasible; hard constraints do.",
                "Equipment parameters and limits come from provenance-tagged "
                "datasheets or benchmark scenario cards.",
            ),
            validity_limits=(
                "The evaluator compares scalar limits and does not interpolate "
                "pump curves, compressor maps, or vessel stress calculations.",
                "Coupled constraints such as pressure-temperature derating and "
                "column hydraulic maps require separate model layers.",
                "Schema version 0.1 accepts finite scalar parameters and "
                "minimum/maximum constraint relations only.",
            ),
            failure_modes=(
                "Unknown equipment types, schemas, duplicate constraints, or "
                "missing provenance fail during card construction/readback.",
                "Missing or nonfinite operating fields fail before evaluation.",
                "Hard violations are returned explicitly and set feasible=false.",
            ),
            units={
                "volume/flow": "m^3; m^3/s",
                "pressure": "Pa",
                "temperature": "K",
                "duty/power/power density": "W; W; W/m^3",
                "speed/NPSH/diameter/height": "1/s; m; m; m",
                "fraction/efficiency/utilization": "dimensionless",
            },
            reference_reading=(
                "IDAES unit-model configuration patterns for equipment type, "
                "design variables, operating bounds, and state constraints",
                "Process equipment datasheet conventions separating mechanical "
                "design limits from normal operating values",
                "JSON-schema-style versioned cards and deterministic validation "
                "used by benchmark artifact contracts",
            ),
            validation_evidence=(
                ValidationEvidence(
                    evidence_id="equipment-card-json-roundtrip",
                    evidence_type="unit_test",
                    description=(
                        "Checks schema-preserving JSON round-trip and exact "
                        "vessel constraint reconstruction."
                    ),
                    status="implemented",
                    command_or_path="tests/test_equipment_specs.py",
                    tolerance="exact dataclass equality",
                ),
                ValidationEvidence(
                    evidence_id="six-equipment-constraint-contracts",
                    evidence_type="unit_test",
                    description=(
                        "Exercises vessel, pump, mixer, condenser, heat "
                        "exchanger, and column cards, including hard and "
                        "warning violations, margins, utilization, and missing fields."
                    ),
                    status="implemented",
                    command_or_path="tests/test_equipment_specs.py",
                    tolerance="exact ids/feasibility and pytest.approx margins",
                ),
            ),
            model_limit_notes=(
                "Lite maturity describes the equipment-card schema only, "
                "not the fidelity of every downstream equipment calculation.",
                "Mechanical design codes, material selection, fatigue, controls, "
                "and vendor guarantees remain outside this schema.",
            ),
            intended_use=(
                "Gym action validation and equipment-aware task generation.",
                "Auditable feasibility, utilization, warning, and hard-limit "
                "features in benchmark trajectories.",
            ),
        ),
    )


__all__ = ["equipment_spec_model_cards"]
