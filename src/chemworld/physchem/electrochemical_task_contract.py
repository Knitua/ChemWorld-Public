"""Canonical scientific contract for the electrochemical-conversion task."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

ELECTROCHEMICAL_WORKFLOW_ADAPTIVE_TWO_STAGE = "adaptive_two_stage"
ELECTROCHEMICAL_WORKFLOW_AUTONOMOUS_OPEN_V1 = "autonomous_open_v1"
ELECTROCHEMICAL_WORKFLOW_STATIC_SINGLE_STAGE = "static_single_stage"
ELECTROCHEMICAL_WORKFLOW_MODES = frozenset(
    {
        ELECTROCHEMICAL_WORKFLOW_ADAPTIVE_TWO_STAGE,
        ELECTROCHEMICAL_WORKFLOW_AUTONOMOUS_OPEN_V1,
        ELECTROCHEMICAL_WORKFLOW_STATIC_SINGLE_STAGE,
    }
)


def normalize_electrochemical_workflow_mode(value: object) -> str:
    mode = str(value)
    if mode not in ELECTROCHEMICAL_WORKFLOW_MODES:
        raise ValueError(
            "electrochemical_workflow_mode must be one of "
            f"{sorted(ELECTROCHEMICAL_WORKFLOW_MODES)}"
        )
    return mode


class _RateLawLike(Protocol):
    @property
    def equation_id(self) -> str: ...

    @property
    def parameters(self) -> Mapping[str, object]: ...


class _ReactionLike(Protocol):
    @property
    def reaction_id(self) -> str: ...

    @property
    def stoichiometry(self) -> Mapping[str, float]: ...

    @property
    def reversible(self) -> bool: ...

    @property
    def rate_law(self) -> _RateLawLike: ...


class _SpeciesLike(Protocol):
    @property
    def species_id(self) -> str: ...

    @property
    def formula(self) -> str: ...

    @property
    def metadata(self) -> Mapping[str, object]: ...


class _NetworkLike(Protocol):
    @property
    def reactions(self) -> Sequence[_ReactionLike]: ...

    @property
    def species(self) -> Sequence[_SpeciesLike]: ...


class _ScoreSpecLike(Protocol):
    @property
    def reactant_species(self) -> str | None: ...

    @property
    def target_species(self) -> Sequence[str]: ...

    @property
    def impurity_species(self) -> Sequence[str]: ...


class _CompiledMechanismLike(Protocol):
    @property
    def mechanism_id(self) -> str: ...

    @property
    def species_index(self) -> Mapping[str, int]: ...

    @property
    def network(self) -> _NetworkLike: ...

    @property
    def score_spec(self) -> _ScoreSpecLike: ...


@dataclass(frozen=True)
class ElectrochemicalTaskContract:
    """Single authority for task identity, accounting, and runtime ownership."""

    contract_version: str = "chemworld-electrochemical-task-contract-0.1"
    task_id: str = "electrochemical-conversion"
    mechanism_id: str = "electrochemical_conversion"
    reactant_species: str = "Ox"
    target_species: str = "Red"
    side_product_species: str = "SideRed"
    desired_pathway_id: str = "desired_redox_couple"
    side_pathway_id: str = "lumped_side_reduction"
    inventory_formula: str = "C6H10O5"
    species_identity_semantics: str = "lumped_redox_pseudocomponents"
    formula_semantics: str = (
        "conserved_element_inventory_basis_not_literal_molecular_formula"
    )
    electron_accounting: str = "implicit_faraday_charge_ledger"
    electrolyte_accounting: str = "boundary_state_outside_redox_species_ledger"
    electrons_transferred: float = 2.0
    standard_potential_V: float = 1.05
    forward_current_sign: int = -1
    setpoint_input_potential_bounds_V: tuple[float, float] = (-3.0, 3.0)
    executable_abs_potential_limit_V: float = 2.5
    setpoint_current_magnitude_bounds_mA: tuple[float, float] = (0.001, 500.0)
    s0_potential_bounds_V: tuple[float, float] = (0.60, 1.80)
    s0_current_magnitude_bounds_mA: tuple[float, float] = (0.001, 220.0)
    runtime_model_ids: tuple[str, ...] = (
        "nernst_butler_volmer_faradaic_v1",
        "runtime_planar_diffusion_layer",
        "runtime_randles_double_layer",
        "aqueous_acid_base_ph_observation",
    )

    @property
    def species_ids(self) -> tuple[str, str, str]:
        return (
            self.reactant_species,
            self.target_species,
            self.side_product_species,
        )

    @property
    def pathway_ids(self) -> tuple[str, str]:
        return (self.desired_pathway_id, self.side_pathway_id)

    def validate_compiled_mechanism(self, compiled: _CompiledMechanismLike) -> None:
        """Fail closed when the declarative mechanism drifts from the runtime."""

        errors: list[str] = []
        if compiled.mechanism_id != self.mechanism_id:
            errors.append(
                f"mechanism_id={compiled.mechanism_id!r}, expected {self.mechanism_id!r}"
            )
        species_ids = set(compiled.species_index)
        if species_ids != set(self.species_ids):
            errors.append(
                f"species={sorted(species_ids)!r}, expected {sorted(self.species_ids)!r}"
            )

        network = compiled.network
        reactions = {reaction.reaction_id: reaction for reaction in network.reactions}
        if set(reactions) != set(self.pathway_ids):
            errors.append(
                f"pathways={sorted(reactions)!r}, expected {sorted(self.pathway_ids)!r}"
            )
        else:
            desired = reactions[self.desired_pathway_id]
            side = reactions[self.side_pathway_id]
            if desired.stoichiometry != {
                self.reactant_species: -1.0,
                self.target_species: 1.0,
            } or not desired.reversible:
                errors.append("desired pathway must declare Ox <=> Red")
            if side.stoichiometry != {
                self.reactant_species: -1.0,
                self.side_product_species: 1.0,
            } or side.reversible:
                errors.append("side pathway must declare Ox => SideRed")
            for reaction in reactions.values():
                if reaction.rate_law.equation_id != "runtime_owned":
                    errors.append(
                        f"pathway {reaction.reaction_id!r} is not runtime_owned"
                    )
                if (
                    reaction.rate_law.parameters.get("runtime_model_id")
                    != "nernst_butler_volmer_faradaic_v1"
                ):
                    errors.append(
                        f"pathway {reaction.reaction_id!r} has the wrong runtime_model_id"
                    )

        score_spec = compiled.score_spec
        if score_spec.reactant_species != self.reactant_species:
            errors.append("score reactant does not match the task contract")
        if tuple(score_spec.target_species) != (self.target_species,):
            errors.append("score target does not match the task contract")
        if tuple(score_spec.impurity_species) != (self.side_product_species,):
            errors.append("score impurity does not match the task contract")

        for species in network.species:
            if species.formula != self.inventory_formula:
                errors.append(
                    f"species {species.species_id!r} has inventory formula {species.formula!r}"
                )
            if species.metadata.get("identity_semantics") != self.species_identity_semantics:
                errors.append(
                    f"species {species.species_id!r} lacks pseudocomponent identity semantics"
                )
            if species.metadata.get("formula_semantics") != self.formula_semantics:
                errors.append(
                    f"species {species.species_id!r} lacks inventory-formula semantics"
                )

        if errors:
            raise ValueError("Electrochemical task contract mismatch: " + "; ".join(errors))

    def provenance(self) -> dict[str, object]:
        return {
            "task_contract_version": self.contract_version,
            "task_id": self.task_id,
            "mechanism_id": self.mechanism_id,
            "runtime_owned_pathway_ids": list(self.pathway_ids),
            "species_identity_semantics": self.species_identity_semantics,
            "formula_semantics": self.formula_semantics,
            "electron_accounting": self.electron_accounting,
            "electrolyte_accounting": self.electrolyte_accounting,
            "current_setpoint_semantics": (
                "nonnegative_magnitude_cap_signed_current_from_butler_volmer"
            ),
        }


ELECTROCHEMICAL_TASK_CONTRACT = ElectrochemicalTaskContract()


__all__ = [
    "ELECTROCHEMICAL_TASK_CONTRACT",
    "ELECTROCHEMICAL_WORKFLOW_ADAPTIVE_TWO_STAGE",
    "ELECTROCHEMICAL_WORKFLOW_AUTONOMOUS_OPEN_V1",
    "ELECTROCHEMICAL_WORKFLOW_MODES",
    "ELECTROCHEMICAL_WORKFLOW_STATIC_SINGLE_STAGE",
    "ElectrochemicalTaskContract",
    "normalize_electrochemical_workflow_mode",
]
