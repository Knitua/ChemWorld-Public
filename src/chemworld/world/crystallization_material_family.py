"""Versioned material families for reaction-to-crystallization optimization."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import Any

HISTORICAL_CRYSTALLIZATION_MATERIAL_FAMILY = (
    "legacy-reaction-crystallization-materials-v0.1"
)
REACTION_CRYSTALLIZATION_LATENT_MATERIAL_FAMILY = (
    "reaction-crystallization-latent-materials-v1"
)
DEFAULT_CRYSTALLIZATION_MATERIAL_FAMILY = (
    HISTORICAL_CRYSTALLIZATION_MATERIAL_FAMILY
)


@dataclass(frozen=True)
class CrystallizationResidualGeneratorContract:
    """Serializable hidden-residual generator for one fixed campaign world."""

    contract_version: str
    seed_namespace: str
    reaction_log_sigma: float
    crystallization_log_sigma: float
    residual_multiplier_bounds: tuple[float, float]

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_version": self.contract_version,
            "seed_namespace": self.seed_namespace,
            "reaction_log_sigma": self.reaction_log_sigma,
            "crystallization_log_sigma": self.crystallization_log_sigma,
            "residual_multiplier_bounds": list(self.residual_multiplier_bounds),
        }


@dataclass(frozen=True)
class CrystallizationMaterialFamily:
    """Public schema and runtime-coupling identity for catalyst/solvent choices."""

    family_id: str
    contract_version: str
    runtime_coupling_version: str
    identity_policy: str
    residual_policy: str
    catalyst_profiles: tuple[Mapping[str, Any], ...]
    solvent_profiles: tuple[Mapping[str, Any], ...]
    residual_generator: CrystallizationResidualGeneratorContract | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "catalyst_profiles",
            tuple(MappingProxyType(dict(row)) for row in self.catalyst_profiles),
        )
        object.__setattr__(
            self,
            "solvent_profiles",
            tuple(MappingProxyType(dict(row)) for row in self.solvent_profiles),
        )

    @property
    def family_sha256(self) -> str:
        encoded = json.dumps(
            self.to_dict(include_hash=False),
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def to_dict(self, *, include_hash: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "family_id": self.family_id,
            "contract_version": self.contract_version,
            "runtime_coupling_version": self.runtime_coupling_version,
            "identity_policy": self.identity_policy,
            "residual_policy": self.residual_policy,
            "catalyst_profiles": [dict(row) for row in self.catalyst_profiles],
            "solvent_profiles": [dict(row) for row in self.solvent_profiles],
            "residual_generator": (
                None
                if self.residual_generator is None
                else self.residual_generator.to_dict()
            ),
        }
        if include_hash:
            payload["family_sha256"] = self.family_sha256
        return payload


_CATALYST_PROFILES = (
    {"reaction_multipliers": [1.00, 1.05, 0.92, 0.95, 0.88]},
    {"reaction_multipliers": [1.30, 0.92, 1.15, 1.08, 1.10]},
    {"reaction_multipliers": [0.82, 1.32, 0.90, 1.18, 0.94]},
    {"reaction_multipliers": [1.10, 0.86, 1.22, 0.90, 1.20]},
)
_SOLVENT_PROFILES = (
    {
        "reaction_multipliers": [0.75, 0.72, 0.68, 0.70, 0.65],
        "solubility_multiplier": 1.20,
        "nucleation_multiplier": 1.25,
        "growth_multiplier": 0.80,
        "impurity_occlusion_multiplier": 1.20,
    },
    {
        "reaction_multipliers": [0.96, 1.02, 1.00, 0.95, 1.05],
        "solubility_multiplier": 0.85,
        "nucleation_multiplier": 0.85,
        "growth_multiplier": 1.05,
        "impurity_occlusion_multiplier": 0.80,
    },
    {
        "reaction_multipliers": [1.20, 0.98, 1.12, 1.15, 0.98],
        "solubility_multiplier": 0.70,
        "nucleation_multiplier": 0.65,
        "growth_multiplier": 1.30,
        "impurity_occlusion_multiplier": 0.65,
    },
    {
        "reaction_multipliers": [1.05, 1.34, 1.28, 1.25, 1.18],
        "solubility_multiplier": 1.05,
        "nucleation_multiplier": 1.05,
        "growth_multiplier": 0.95,
        "impurity_occlusion_multiplier": 1.05,
    },
)
_RESIDUAL_GENERATOR = CrystallizationResidualGeneratorContract(
    contract_version="chemworld-reaction-crystallization-residual-generator-1.0",
    seed_namespace="reaction-crystallization-latent-materials-v1-residuals",
    reaction_log_sigma=0.12,
    crystallization_log_sigma=0.08,
    residual_multiplier_bounds=(0.75, 1.35),
)

_FAMILIES = {
    HISTORICAL_CRYSTALLIZATION_MATERIAL_FAMILY: CrystallizationMaterialFamily(
        family_id=HISTORICAL_CRYSTALLIZATION_MATERIAL_FAMILY,
        contract_version="chemworld-reaction-crystallization-material-family-0.1",
        runtime_coupling_version="legacy-shared-reaction-effects-and-global-crystal-law-v0.1",
        identity_policy="historical categorical benchmark choices",
        residual_policy="legacy shared world tables; historical replay only",
        catalyst_profiles=(),
        solvent_profiles=(),
    ),
    REACTION_CRYSTALLIZATION_LATENT_MATERIAL_FAMILY: CrystallizationMaterialFamily(
        family_id=REACTION_CRYSTALLIZATION_LATENT_MATERIAL_FAMILY,
        contract_version="chemworld-reaction-crystallization-material-family-1.0",
        runtime_coupling_version="reaction-and-population-balance-material-coupling-v1",
        identity_policy=(
            "Catalyst and solvent IDs are anonymous benchmark formulations, not real "
            "synthesis recommendations."
        ),
        residual_policy=(
            "Nominal reaction and crystallization factors receive bounded, correlated-"
            "by-choice residuals sampled once per world and fixed for the campaign."
        ),
        catalyst_profiles=_CATALYST_PROFILES,
        solvent_profiles=_SOLVENT_PROFILES,
        residual_generator=_RESIDUAL_GENERATOR,
    ),
}


def normalize_crystallization_material_family(value: object | None) -> str:
    family_id = DEFAULT_CRYSTALLIZATION_MATERIAL_FAMILY if value is None else str(value)
    if family_id not in _FAMILIES:
        raise ValueError(
            f"crystallization material family must be one of {sorted(_FAMILIES)}"
        )
    return family_id


def crystallization_material_family(
    value: object | None,
) -> CrystallizationMaterialFamily:
    return _FAMILIES[normalize_crystallization_material_family(value)]


def apply_crystallization_material_family(instance: Any, value: object | None) -> Any:
    """Bind the non-legacy family only to reaction-to-crystallization worlds."""

    family = crystallization_material_family(value)
    if family.family_id == HISTORICAL_CRYSTALLIZATION_MATERIAL_FAMILY:
        return instance
    if instance.spec.scenario_id != "reaction-to-crystallization":
        raise ValueError(
            "non-legacy crystallization material families require the "
            "reaction-to-crystallization task"
        )
    instance_sha256 = crystallization_material_instance_sha256(
        instance.parameters,
        family,
    )
    initial_state = instance.initial_state.replace(
        metadata={
            **instance.initial_state.metadata,
            "crystallization_material_family_id": family.family_id,
            "crystallization_material_family_sha256": family.family_sha256,
            "crystallization_material_family_contract_version": family.contract_version,
            "crystallization_material_instance_sha256": instance_sha256,
        }
    )
    parameters = replace(
        instance.parameters,
        world_id=(
            f"{instance.parameters.world_id}:crystal-materials-"
            f"{family.family_sha256[:12]}:instance-{instance_sha256[:12]}"
        ),
        provider=f"{instance.parameters.provider}+crystallization-material-family",
    )
    return replace(instance, parameters=parameters, initial_state=initial_state)


def crystallization_material_instance_sha256(
    parameters: Any,
    family: CrystallizationMaterialFamily,
) -> str:
    def _value(value: Any) -> Any:
        return value.tolist() if hasattr(value, "tolist") else value

    payload = {
        "family_sha256": family.family_sha256,
        "world_id": parameters.world_id,
        "catalyst_effects": _value(parameters.crystallization_catalyst_effects),
        "solvent_reaction_effects": _value(
            parameters.crystallization_solvent_effects
        ),
        "solvent_solubility": _value(
            parameters.crystallization_solvent_solubility_multipliers
        ),
        "solvent_nucleation": _value(
            parameters.crystallization_solvent_nucleation_multipliers
        ),
        "solvent_growth": _value(
            parameters.crystallization_solvent_growth_multipliers
        ),
        "solvent_occlusion": _value(
            parameters.crystallization_solvent_occlusion_multipliers
        ),
        "reference_solubility_mol_L": (
            parameters.crystallization_reference_solubility_mol_L
        ),
    }
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


__all__ = [
    "DEFAULT_CRYSTALLIZATION_MATERIAL_FAMILY",
    "HISTORICAL_CRYSTALLIZATION_MATERIAL_FAMILY",
    "REACTION_CRYSTALLIZATION_LATENT_MATERIAL_FAMILY",
    "CrystallizationMaterialFamily",
    "CrystallizationResidualGeneratorContract",
    "apply_crystallization_material_family",
    "crystallization_material_family",
    "crystallization_material_instance_sha256",
    "normalize_crystallization_material_family",
]
