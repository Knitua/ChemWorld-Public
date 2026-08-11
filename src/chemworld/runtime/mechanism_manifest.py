"""Mechanism manifest and compiled-mechanism data contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from chemworld.physchem.reaction_network import ReactionNetworkSpec
from chemworld.schemas import SchemaValidationResult


@dataclass(frozen=True)
class ScoreSpec:
    target_species: tuple[str, ...]
    impurity_species: tuple[str, ...]
    initial_limiting_species: str | None

    @property
    def reactant_species(self) -> str | None:
        return self.initial_limiting_species

    @property
    def product_species(self) -> str | None:
        return self.target_species[0] if self.target_species else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_species": list(self.target_species),
            "impurity_species": list(self.impurity_species),
            "initial_limiting_species": self.initial_limiting_species,
        }


@dataclass(frozen=True)
class MechanismValidationReport:
    mechanism_id: str
    schema_version: str
    mechanism_hash: str
    source_path: str
    passed: bool
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    species_count: int
    reaction_count: int
    rate_law_equation_ids: tuple[str, ...]

    @classmethod
    def from_schema_result(
        cls,
        *,
        mechanism_id: str,
        schema_version: str,
        mechanism_hash: str,
        source_path: str,
        schema_result: SchemaValidationResult,
        payload: dict[str, Any],
    ) -> MechanismValidationReport:
        reactions = payload.get("reactions", ())
        species = payload.get("species", ())
        rate_laws: set[str] = set()
        if isinstance(reactions, list):
            for reaction in reactions:
                if not isinstance(reaction, dict):
                    continue
                rate_law = reaction.get("rate_law", {})
                if isinstance(rate_law, dict):
                    equation_id = rate_law.get("equation_id", "")
                    if equation_id:
                        rate_laws.add(str(equation_id))
        return cls(
            mechanism_id=mechanism_id,
            schema_version=schema_version,
            mechanism_hash=mechanism_hash,
            source_path=source_path,
            passed=schema_result.valid,
            errors=schema_result.errors,
            warnings=schema_result.warnings,
            species_count=len(species) if isinstance(species, list) else 0,
            reaction_count=len(reactions) if isinstance(reactions, list) else 0,
            rate_law_equation_ids=tuple(sorted(rate_laws)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "mechanism_id": self.mechanism_id,
            "schema_version": self.schema_version,
            "mechanism_hash": self.mechanism_hash,
            "source_path": self.source_path,
            "passed": self.passed,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "species_count": self.species_count,
            "reaction_count": self.reaction_count,
            "rate_law_equation_ids": list(self.rate_law_equation_ids),
        }


@dataclass(frozen=True)
class MechanismManifest:
    mechanism_id: str
    mechanism_version: str
    mechanism_hash: str
    source_path: str
    species_count: int
    reaction_count: int
    rate_law_equation_ids: tuple[str, ...]
    species_roles: dict[str, tuple[str, ...]]
    observable_mapping: dict[str, tuple[str, ...]]
    score_spec: ScoreSpec
    initial_amount_policy: dict[str, float]
    validation_report: MechanismValidationReport

    def to_dict(self) -> dict[str, Any]:
        return {
            "mechanism_id": self.mechanism_id,
            "mechanism_version": self.mechanism_version,
            "mechanism_hash": self.mechanism_hash,
            "source_path": self.source_path,
            "species_count": self.species_count,
            "reaction_count": self.reaction_count,
            "rate_law_equation_ids": list(self.rate_law_equation_ids),
            "species_roles": {
                species_id: list(roles) for species_id, roles in self.species_roles.items()
            },
            "observable_mapping": {
                role: list(species) for role, species in self.observable_mapping.items()
            },
            "score_spec": self.score_spec.to_dict(),
            "initial_amount_policy": dict(self.initial_amount_policy),
            "validation_report": self.validation_report.to_dict(),
        }


@dataclass(frozen=True)
class CompiledMechanism:
    mechanism_id: str
    mechanism_version: str
    mechanism_hash: str
    network: ReactionNetworkSpec
    species_index: dict[str, int]
    stoichiometric_matrix: tuple[tuple[float, ...], ...]
    reaction_enthalpies: dict[str, float]
    species_roles: dict[str, tuple[str, ...]]
    observable_mapping: dict[str, tuple[str, ...]]
    score_spec: ScoreSpec
    initial_amount_policy: dict[str, float]
    manifest: MechanismManifest

    def to_dict(self) -> dict[str, Any]:
        return {
            "mechanism_id": self.mechanism_id,
            "mechanism_version": self.mechanism_version,
            "mechanism_hash": self.mechanism_hash,
            "species_index": dict(self.species_index),
            "stoichiometric_matrix": [list(row) for row in self.stoichiometric_matrix],
            "reaction_enthalpies": dict(self.reaction_enthalpies),
            "species_roles": {
                species_id: list(roles) for species_id, roles in self.species_roles.items()
            },
            "observable_mapping": {
                key: list(value) for key, value in self.observable_mapping.items()
            },
            "score_spec": self.score_spec.to_dict(),
            "initial_amount_policy": dict(self.initial_amount_policy),
            "manifest": self.manifest.to_dict(),
        }


__all__ = [
    "CompiledMechanism",
    "MechanismManifest",
    "MechanismValidationReport",
    "ScoreSpec",
]
