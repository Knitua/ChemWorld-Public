"""Model card for deterministic electrochemical scenario generation."""

from __future__ import annotations

from chemworld.physchem.maturity import MaturityLevel, ModelCard, ValidationEvidence


def electrochemical_scenario_model_cards() -> tuple[ModelCard, ...]:
    return (
        ModelCard(
            model_id="electrochemical_scenario_card_generation_v1",
            module_id="electrochemistry",
            title="Electrochemical Scenario Cards And Hidden-Parameter Generation",
            maturity=MaturityLevel.LITE,
            summary=(
                "Versioned public redox/equipment/window cards with private "
                "parameter ranges, split-aware deterministic sampling, side-"
                "reaction thresholds, and direct construction of standalone model bundles. "
                "This catalog is not the electrochemical-conversion task runtime."
            ),
            equations=(
                "seed = SHA256(schema:scenario:split:seed:private_salt)",
                "uniform sample = U(minimum, maximum)",
                "log-uniform sample = 10^U(log10(minimum), log10(maximum))",
                "hidden digest = SHA256(canonical hidden-parameter mapping)",
                "side-reaction severity = distance beyond onset / distance to window edge",
            ),
            assumptions=(
                "Public cards expose redox metadata, geometry, electrolyte "
                "window, side-reaction onsets, qualitative behavior, and hidden "
                "parameter names/distribution families.",
                "Hidden range endpoints and generated values remain private.",
                "public-dev, public-test, and private-eval share the same model "
                "family but use distinct deterministic seed payloads.",
                "private-eval generation requires a maintainer-controlled salt.",
                "Generated bundles are standalone references and are not loaded by "
                "ChemWorldElectrochemicalServices.",
            ),
            validity_limits=(
                "Generated parameters are bounded independent samples; cross-"
                "parameter correlations require a future joint distribution.",
                "Side-reaction severity is a threshold-distance screening metric.",
                "Curated cards cover one tracked redox reaction and one electrode "
                "geometry per scenario.",
            ),
            failure_modes=(
                "Misordered electrolyte windows/onsets, incomplete hidden ranges, "
                "fraction ranges above one, and unsupported splits fail early.",
                "private-eval without a salt fails rather than using a public placeholder.",
                "Public serialization excludes hidden ranges and instance values.",
            ),
            units={
                "standard/onset/window potential": "V",
                "electrode area/gap/electrolyte volume": "m^2; m; m^3",
                "sampled electrochemical parameters": "units declared by field suffix",
                "side-reaction severity": "dimensionless",
                "hidden digest": "64-character lowercase SHA-256 hex",
            },
            reference_reading=(
                "Electrochemical experiment metadata conventions for redox "
                "couples, electrode geometry, electrolyte windows, and side reactions",
                "Benchmark public/private split policies with salted hidden parameters",
                "Event/model-card architecture separating public scenario semantics "
                "from private generated physical parameters",
            ),
            validation_evidence=(
                ValidationEvidence(
                    evidence_id="electrochemical-card-public-private-boundary",
                    evidence_type="unit_test",
                    description=(
                        "Checks curated card ids, public exclusion of range bounds/"
                        "values, private range completeness, deterministic generation, "
                        "split sensitivity, bounds, and mandatory private salt."
                    ),
                    status="implemented",
                    command_or_path="tests/test_electrochemical_scenarios.py",
                    tolerance="exact public keys/determinism and bounded samples",
                ),
                ValidationEvidence(
                    evidence_id="electrochemical-card-model-bundle-and-thresholds",
                    evidence_type="unit_test",
                    description=(
                        "Checks consistent reaction/resistance/diffusion/double-"
                        "layer specs, shared area/provenance, and selective/side-"
                        "reaction/window-exceeded classifications."
                    ),
                    status="implemented",
                    command_or_path="tests/test_electrochemical_scenarios.py",
                    tolerance="pytest.approx shared parameters and exact flags",
                ),
            ),
            model_limit_notes=(
                "Lite maturity applies to the scenario-generation and "
                "visibility contract, not universal electrochemical chemistry.",
                "Multi-reaction mechanisms, correlated posteriors, electrode "
                "morphology, electrolyte speciation, and validated parameter "
                "databases remain external.",
            ),
            intended_use=(
                "Standalone public/private electrochemical reference generation.",
                "Agent generalization studies across redox, transport, ohmic, "
                "double-layer, selectivity, and side-reaction uncertainty.",
            ),
        ),
    )


__all__ = ["electrochemical_scenario_model_cards"]
