"""Model cards for identity, dimension, and data-governance infrastructure."""

from __future__ import annotations

from chemworld.physchem.maturity import MaturityLevel, ModelCard, ValidationEvidence


def data_foundation_model_cards() -> tuple[ModelCard, ...]:
    return (
        ModelCard(
            model_id="component_identity_registry_v1",
            module_id="data_foundation",
            title="Versioned Component Identity Registry",
            maturity=MaturityLevel.REFERENCE_VALIDATED,
            summary=(
                "Immutable component registry with canonical identifiers, aliases, "
                "checksum-validated CAS numbers, InChI/InChIKey identities, formula, "
                "charge, formula-checked molecular weight, provenance, and SHA-256."
            ),
            equations=(
                "molecular weight = sum(element count * standard atomic weight)",
                "registry digest = SHA-256(canonical JSON payload)",
            ),
            assumptions=(
                "Component identities describe benchmark substances rather than "
                "stereochemical or tautomer-resolution policy.",
                "Property correlations remain separate from identity records.",
            ),
            validity_limits=(
                "The curated built-in registry contains six reference-checked compounds.",
                "InChI shape validation does not replace the official InChI toolkit.",
            ),
            failure_modes=(
                "Duplicate identifiers, aliases, CAS numbers, InChI strings, or "
                "InChIKeys fail registry construction.",
                "Invalid CAS checksum, formula, molecular weight, or registry digest "
                "fails readback.",
            ),
            units={"molecular_weight": "g/mol", "charge": "elementary-charge count"},
            reference_reading=(
                "IUPAC InChI/InChIKey identifier conventions.",
                "CAS Registry Number check-digit convention.",
            ),
            validation_evidence=(
                ValidationEvidence(
                    evidence_id="component-registry-roundtrip",
                    evidence_type="unit_test",
                    description=(
                        "Checks all identity lookup modes, collision rejection, "
                        "digest verification, and exact JSON round-trip."
                    ),
                    status="implemented",
                    command_or_path="tests/test_data_foundations.py",
                    tolerance="exact",
                ),
            ),
            model_limit_notes=(
                "This is identity and provenance infrastructure, not a broad chemical "
                "database or structure-search engine.",
            ),
            intended_use=(
                "Stable component lookup across property, reaction, task, and dataset records.",
            ),
        ),
        ModelCard(
            model_id="canonical_dimension_checker_v1",
            module_id="data_foundation",
            title="Canonical Unit-Dimension Checker",
            maturity=MaturityLevel.LITE,
            summary=(
                "Semantic dimension catalog and exponent algebra spanning base process "
                "quantities, thermodynamic/transport properties, electrochemistry, "
                "spectroscopy, chromatography, NMR, MS, cost, and risk."
            ),
            equations=(
                "[pressure] = M L^-1 T^-2",
                "[energy] = M L^2 T^-2",
                "[diffusivity] = L^2 T^-1",
                "dimension products/divisions add/subtract base-axis exponents",
            ),
            assumptions=(
                "Unit conversion remains in foundation.units; this layer checks "
                "semantic dimensions and field allowlists.",
                "Arbitrary detector counts use an explicit signal axis.",
            ),
            validity_limits=(
                "Only units registered in the ChemWorld unit table are accepted.",
                "Chemical shift, absorbance, and m/z are dimensionless physically but "
                "retain distinct semantic dimensions to prevent field swaps.",
            ),
            failure_modes=(
                "Unknown units/dimensions and semantic mismatches fail in strict mode.",
                "Field contracts reject dimension-compatible units outside their allowlist.",
            ),
            units={"dimension_vector": "integer SI/semantic base-axis exponents"},
            reference_reading=(
                "SI Brochure dimensional-quantity conventions.",
                "IUPAC Green Book quantity and unit conventions.",
            ),
            validation_evidence=(
                ValidationEvidence(
                    evidence_id="dimension-catalog-closure",
                    evidence_type="unit_test",
                    description=(
                        "Checks every supported unit maps to a canonical dimension, "
                        "dimension algebra, instrument semantics, and strict failures."
                    ),
                    status="implemented",
                    command_or_path="tests/test_data_foundations.py",
                    tolerance="exact",
                ),
            ),
            model_limit_notes=(
                "This checker is deliberately compact and does not parse arbitrary unit strings.",
            ),
            intended_use=(
                "Schema validation for model inputs, equipment cards, instruments, and datasets.",
            ),
        ),
        ModelCard(
            model_id="deterministic_data_conflict_policy_v1",
            module_id="data_foundation",
            title="Deterministic Data Conflict And Provenance Policy",
            maturity=MaturityLevel.LITE,
            summary=(
                "Source-ranked field resolution with absolute/relative tolerance, "
                "uncertainty requirements, warning versus hard-fail findings, "
                "canonical digests, and dataset provenance cards."
            ),
            equations=(
                "consistent iff |a-b| <= atol + rtol*|selected|",
                "report/card digest = SHA-256(canonical JSON payload)",
            ),
            assumptions=(
                "Source priority is explicit policy, never inferred from input order.",
                "Uncertainty metadata is field-scoped and may be required by policy.",
            ),
            validity_limits=(
                "Numeric fields use scalar tolerances; structured values use exact equality.",
                "Scientific source quality must be encoded by maintainers in source priority.",
            ),
            failure_modes=(
                "Undefined sources and raise-mode conflicts produce hard-fail findings.",
                "Required missing uncertainty can warn or hard-fail by policy.",
                "Digest mismatch fails report or dataset-card readback.",
            ),
            units={"rtol": "dimensionless", "atol": "field unit"},
            reference_reading=(
                "FAIR data provenance and machine-actionable dataset-card practices.",
            ),
            validation_evidence=(
                ValidationEvidence(
                    evidence_id="data-conflict-audit-roundtrip",
                    evidence_type="unit_test",
                    description=(
                        "Checks order-independent priority, uncertainty policy, "
                        "warning/error reports, source provenance, and card digests."
                    ),
                    status="implemented",
                    command_or_path="tests/test_data_foundations.py",
                    tolerance="exact and declared scalar tolerances",
                ),
            ),
            model_limit_notes=(
                "The policy makes governance auditable; it does not decide which "
                "scientific database should be authoritative for every property family.",
            ),
            intended_use=("Curated component/property ingestion and release dataset provenance.",),
        ),
    )


__all__ = ["data_foundation_model_cards"]
