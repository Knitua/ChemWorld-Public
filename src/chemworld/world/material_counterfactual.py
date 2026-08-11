"""Hidden material-law counterfactuals with an unchanged public interface."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from typing import Any, Literal, cast

import numpy as np

from chemworld.world.actions import ELECTROLYTE_PROFILES
from chemworld.world.scenario import ScenarioInstance

MaterialField = Literal["catalyst", "solvent", "electrolyte_profile"]

MATERIAL_LAW_COUNTERFACTUAL_VERSION = "chemworld-material-law-counterfactual-0.2"
_HIDDEN_FIELD_KEY = "_hidden_material_law_counterfactual_field"
_HIDDEN_MAPPING_KEY = "_hidden_material_law_public_to_baseline"


@dataclass(frozen=True)
class MaterialLawCounterfactual:
    """Permute hidden material effects without changing public names or codes."""

    material_field: MaterialField
    public_to_baseline: tuple[int, ...]

    def __post_init__(self) -> None:
        if self.material_field not in {"catalyst", "solvent", "electrolyte_profile"}:
            raise ValueError("material_field must be catalyst, solvent, or electrolyte_profile")
        if sorted(self.public_to_baseline) != list(range(len(self.public_to_baseline))):
            raise ValueError("public_to_baseline must be a permutation of [0, n)")
        if all(index == value for index, value in enumerate(self.public_to_baseline)):
            raise ValueError("material-law counterfactual must be non-identity")

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> MaterialLawCounterfactual:
        if payload.get("kind") != "material_law_counterfactual":
            raise ValueError(
                "material-law counterfactual kind must be 'material_law_counterfactual'"
            )
        raw_permutation = payload.get("public_to_baseline")
        if not isinstance(raw_permutation, list) or not all(
            isinstance(value, int) and not isinstance(value, bool) for value in raw_permutation
        ):
            raise ValueError("public_to_baseline must be a list of integers")
        return cls(
            material_field=cast(MaterialField, str(payload.get("material_field"))),
            public_to_baseline=tuple(raw_permutation),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": "material_law_counterfactual",
            "material_field": self.material_field,
            "public_to_baseline": list(self.public_to_baseline),
        }


def material_law_counterfactual_hash(
    counterfactual: MaterialLawCounterfactual,
) -> str:
    payload = {
        "version": MATERIAL_LAW_COUNTERFACTUAL_VERSION,
        "counterfactual": counterfactual.to_dict(),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def apply_material_law_counterfactual(
    instance: ScenarioInstance,
    counterfactual: MaterialLawCounterfactual,
) -> ScenarioInstance:
    """Execute swapped hidden effects while holding public material facts fixed.

    Only kinetic-effect rows are permuted. Public names, action schemas, costs,
    risks, and all non-material hidden parameters remain unchanged.
    """

    parameters = instance.parameters
    catalyst_effects = np.array(parameters.catalyst_effects, copy=True)
    solvent_effects = np.array(parameters.solvent_effects, copy=True)
    if counterfactual.material_field == "catalyst":
        target_count = catalyst_effects.shape[0]
    elif counterfactual.material_field == "solvent":
        target_count = solvent_effects.shape[0]
    else:
        target_count = len(ELECTROLYTE_PROFILES)
    if len(counterfactual.public_to_baseline) != target_count:
        raise ValueError(
            "material-law permutation length does not match the selected material catalog"
        )
    if counterfactual.material_field == "catalyst":
        catalyst_effects = catalyst_effects[
            np.asarray(counterfactual.public_to_baseline, dtype=int),
            :,
        ]
    elif counterfactual.material_field == "solvent":
        solvent_effects = solvent_effects[
            np.asarray(counterfactual.public_to_baseline, dtype=int),
            :,
        ]

    contract_hash = material_law_counterfactual_hash(counterfactual)
    parameters = replace(
        parameters,
        world_id=f"{parameters.world_id}:material-law-{contract_hash[:12]}",
        provider=f"{parameters.provider}+material-law-counterfactual",
        catalyst_effects=catalyst_effects,
        solvent_effects=solvent_effects,
    )
    state = instance.initial_state.replace(
        metadata={
            **instance.initial_state.metadata,
            "material_law_counterfactual_version": (MATERIAL_LAW_COUNTERFACTUAL_VERSION),
            "material_law_counterfactual_hash": contract_hash,
            _HIDDEN_FIELD_KEY: counterfactual.material_field,
            _HIDDEN_MAPPING_KEY: list(counterfactual.public_to_baseline),
        }
    )
    return replace(instance, parameters=parameters, initial_state=state)


def resolve_material_law_index(
    metadata: dict[str, Any],
    *,
    material_field: MaterialField,
    public_index: int,
    catalog_size: int,
) -> int:
    """Resolve one public material label to its hidden baseline-effect row."""

    if not 0 <= public_index < catalog_size:
        raise ValueError("public material index is outside the declared catalog")
    if metadata.get(_HIDDEN_FIELD_KEY) != material_field:
        return public_index
    raw_mapping = metadata.get(_HIDDEN_MAPPING_KEY)
    if not isinstance(raw_mapping, list) or not all(
        isinstance(item, int) and not isinstance(item, bool) for item in raw_mapping
    ):
        raise ValueError("hidden material-law mapping is malformed")
    if len(raw_mapping) != catalog_size or sorted(raw_mapping) != list(range(catalog_size)):
        raise ValueError("hidden material-law mapping does not match the public catalog")
    return int(raw_mapping[public_index])


__all__ = [
    "MATERIAL_LAW_COUNTERFACTUAL_VERSION",
    "MaterialLawCounterfactual",
    "apply_material_law_counterfactual",
    "material_law_counterfactual_hash",
    "resolve_material_law_index",
]
