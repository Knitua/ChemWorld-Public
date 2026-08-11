"""Mechanism YAML hashing, schema validation, and runtime role checks."""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from typing import Any

import yaml

from chemworld.physchem.mechanism_library import MechanismScenarioCard
from chemworld.physchem.reaction_network import ReactionNetworkSpec
from chemworld.runtime.mechanism_manifest import MechanismValidationReport
from chemworld.schemas import validate_mechanism_schema


def mechanism_hash(path: str | Path) -> str:
    payload = raw_mechanism_payload(Path(path))
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return sha256(canonical.encode("utf-8")).hexdigest()


def validate_mechanism_file(path: str | Path) -> MechanismValidationReport:
    path = Path(path)
    payload = raw_mechanism_payload(path)
    schema_result = validate_mechanism_schema(payload)
    report = MechanismValidationReport.from_schema_result(
        mechanism_id=str(payload.get("network_id", "")),
        schema_version=str(payload.get("schema_version", "")),
        mechanism_hash=mechanism_hash(path),
        source_path=path.as_posix(),
        schema_result=schema_result,
        payload=payload,
    )
    if not report.passed:
        raise ValueError(
            f"Mechanism {path} does not satisfy schema contract: "
            + "; ".join(report.errors)
        )
    return report


def raw_mechanism_payload(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Mechanism file must contain a mapping: {path}")
    return payload


def build_observable_mapping(
    network: ReactionNetworkSpec,
    card: MechanismScenarioCard,
) -> dict[str, tuple[str, ...]]:
    roles: dict[str, list[str]] = {
        "reactant": [],
        "target": list(card.target_species),
        "impurity": list(card.impurity_species),
        "product": list(card.target_species),
        "byproduct": [],
        "degradation": [],
        "catalyst": [],
    }
    for species in network.species:
        aliases = set(species.observable_aliases)
        if "reactant" in aliases or "oxidized_reactant" in aliases:
            roles["reactant"].append(species.species_id)
        if "side_product" in aliases or "byproduct" in aliases:
            roles["byproduct"].append(species.species_id)
        if "degradation_product" in aliases or species.species_id.lower().startswith("d"):
            roles["degradation"].append(species.species_id)
        if species.catalyst or "catalyst" in aliases:
            roles["catalyst"].append(species.species_id)
    return {key: tuple(dict.fromkeys(value)) for key, value in roles.items()}


def initial_limiting_species(card: MechanismScenarioCard) -> str | None:
    positive = [
        species_id
        for species_id, amount in card.initial_amounts_mol.items()
        if amount > 0.0
    ]
    return positive[0] if positive else None


def validate_compiled_role_contract(
    network: ReactionNetworkSpec,
    card: MechanismScenarioCard,
    *,
    observable_mapping: dict[str, tuple[str, ...]],
    initial_limiting_species: str | None,
    require_runtime_roles: bool,
) -> None:
    species_ids = set(network.species_ids)
    errors: list[str] = []

    if not card.target_species:
        errors.append("target_species cannot be empty")
    if require_runtime_roles and not card.impurity_species:
        errors.append("impurity_species cannot be empty for runtime scoring")
    if initial_limiting_species is None:
        errors.append("initial_amounts_mol must contain at least one positive species")

    unknown_initial = sorted(set(card.initial_amounts_mol) - species_ids)
    if unknown_initial:
        errors.append(f"initial species not in mechanism: {unknown_initial}")
    unknown_target = sorted(set(card.target_species) - species_ids)
    if unknown_target:
        errors.append(f"target species not in mechanism: {unknown_target}")
    unknown_impurity = sorted(set(card.impurity_species) - species_ids)
    if unknown_impurity:
        errors.append(f"impurity species not in mechanism: {unknown_impurity}")
    if initial_limiting_species is not None and initial_limiting_species not in species_ids:
        errors.append(f"initial limiting species not in mechanism: {initial_limiting_species!r}")

    for role, species in observable_mapping.items():
        unknown_role_species = sorted(set(species) - species_ids)
        if unknown_role_species:
            errors.append(
                f"observable role {role!r} contains unknown species: {unknown_role_species}"
            )

    if initial_limiting_species is not None:
        reactants = observable_mapping.get("reactant", ())
        if reactants and initial_limiting_species not in reactants:
            errors.append(
                "initial limiting species must be included in observable reactant role "
                f"when reactants are declared: {initial_limiting_species!r}"
            )

    if errors:
        raise ValueError(
            f"Mechanism {card.mechanism_id!r} does not satisfy the runtime role contract: "
            + "; ".join(errors)
        )


__all__ = [
    "build_observable_mapping",
    "initial_limiting_species",
    "mechanism_hash",
    "raw_mechanism_payload",
    "validate_compiled_role_contract",
    "validate_mechanism_file",
]
