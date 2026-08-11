"""Runtime construction and deterministic execution for Work I world forks.

The runtime deliberately separates evaluator-owned world identity from the
agent-facing contract.  A fork is built from two real ``ChemWorldEnv``
instances, hashed over the frozen F01 component inventory, and exercised with
the same typed action sequence on both sides.
"""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import gymnasium as gym
import numpy as np

import chemworld  # noqa: F401  # register the Gym environment
from chemworld.agents.task_recipes import (
    task_recipe_dimension,
    task_recipe_from_unit_vector,
)
from chemworld.foundation.world_fork_manifest import (
    InterventionClass,
    WorldComponentInventory,
    canonical_json_sha256,
)
from chemworld.foundation.world_fork_public_contract import (
    PublicContractBundle,
    build_public_contract_bundle,
)
from chemworld.foundation.world_fork_spec import WorldForkSpec, build_world_fork_spec
from chemworld.world.instruments import instrument_contracts
from chemworld.world.world_law import constitution_rules

WORLD_FORK_TRACE_SCHEMA_VERSION = "chemworld-world-fork-runtime-trace-0.1"
WORLD_FORK_RUNTIME_SCHEMA_VERSION = "chemworld-world-fork-runtime-result-0.1"

PUBLIC_TRANSACTION_STATUS_SEMANTICS = (
    {
        "status": "committed",
        "stage": "runtime_transaction",
        "physical_candidate_committed": True,
        "attempt_may_be_charged": True,
    },
    {
        "status": "validation_failed",
        "stage": "action_or_domain_validation",
        "physical_candidate_committed": False,
        "attempt_may_be_charged": True,
    },
    {
        "status": "rolled_back",
        "stage": "precondition_or_constitution",
        "physical_candidate_committed": False,
        "attempt_may_be_charged": True,
    },
    {
        "status": "campaign_resource_rejected",
        "stage": "campaign_resource_preflight",
        "physical_candidate_committed": False,
        "attempt_may_be_charged": True,
    },
)

_INTERVENTION_METADATA_TOKENS = (
    "intervention",
    "counterfactual",
    "derived_constitutive",
    "_hidden_material_law",
)
_MATERIAL_PARAMETER_FIELDS = (
    "crystallization_catalyst_effects",
    "crystallization_reference_solubility_mol_L",
    "crystallization_solvent_effects",
    "crystallization_solvent_growth_multipliers",
    "crystallization_solvent_nucleation_multipliers",
    "crystallization_solvent_occlusion_multipliers",
    "crystallization_solvent_solubility_multipliers",
    "electrochemical_base_contact_resistance_ohm",
    "electrochemical_electrode_area_m2",
    "electrochemical_electrode_gap_m",
    "electrochemical_electrolyte_effects",
    "electrochemical_electrolyte_potential_residual_V",
    "electrochemical_exchange_current_density_A_m2",
    "electrochemical_solvent_effects",
    "electrochemical_solvent_potential_residual_V",
)


class WorldForkRuntimeError(RuntimeError):
    """Raised when a declared fork cannot be built or executed faithfully."""


def _json_value(value: Any) -> Any:
    """Convert runtime values to finite, deterministic JSON data."""

    if dataclasses.is_dataclass(value):
        return {
            field.name: _json_value(getattr(value, field.name))
            for field in dataclasses.fields(value)
        }
    if isinstance(value, np.ndarray):
        return _json_value(value.tolist())
    if isinstance(value, np.generic):
        return _json_value(value.item())
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in sorted(value.items())}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_json_value(item) for item in value]
    if isinstance(value, float) and not np.isfinite(value):
        # Missing observation channels are represented as NaN inside Gym arrays;
        # the public trace uses JSON null as their explicit wire representation.
        return None
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if hasattr(value, "to_dict"):
        return _json_value(value.to_dict())
    raise WorldForkRuntimeError(f"unsupported runtime payload type: {type(value).__name__}")


def _without_intervention_metadata(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        str(key): _json_value(value)
        for key, value in sorted(payload.items())
        if not any(token in str(key) for token in _INTERVENTION_METADATA_TOKENS)
    }


def _checkout_independent_sources(value: Any) -> Any:
    """Normalize provenance paths without removing the referenced source identity."""

    if isinstance(value, Mapping):
        normalized: dict[str, Any] = {}
        for key, item in sorted(value.items()):
            if key == "source_path" and isinstance(item, str):
                source = item.replace("\\", "/")
                marker = "/configs/"
                normalized[str(key)] = (
                    f"configs/{source.split(marker, 1)[1]}" if marker in source else source
                )
            else:
                normalized[str(key)] = _checkout_independent_sources(item)
        return normalized
    if isinstance(value, list):
        return [_checkout_independent_sources(item) for item in value]
    return value


def _stable_numeric_projection(value: Any) -> Any:
    """Remove platform-level roundoff below the trace's measurement precision."""

    if isinstance(value, Mapping):
        return {
            str(key): _stable_numeric_projection(item)
            for key, item in sorted(value.items())
        }
    if isinstance(value, list):
        return [_stable_numeric_projection(item) for item in value]
    if isinstance(value, float):
        return round(value, 14)
    return value


def _initial_condition_payload(env: Any) -> dict[str, Any]:
    state = _json_value(env.scenario_instance.initial_state.to_dict(include_hidden=True))
    state["metadata"] = _without_intervention_metadata(state.get("metadata", {}))
    return {
        "scenario_initial_state_id": env.scenario_instance.spec.initial_state_id,
        "state": state,
    }


def _material_mapping_payload(env: Any) -> dict[str, Any]:
    metadata = env.scenario_instance.initial_state.metadata
    field = metadata.get("_hidden_material_law_counterfactual_field")
    mapping = metadata.get("_hidden_material_law_public_to_baseline")
    if field is None:
        if env.task_id == "electrochemical-conversion":
            field = "electrolyte_profile"
        elif env.task_id == "reaction-to-crystallization":
            field = "catalyst_and_solvent"
        else:
            field = "none"
    if mapping is None:
        mapping = [0, 1, 2, 3]
    return {
        "material_field": str(field),
        "public_to_baseline": _json_value(mapping),
    }


def _component_payloads(env: Any) -> dict[str, dict[str, Any]]:
    """Extract every non-identity F01 component from a live reset environment."""

    parameters = env.scenario_instance.parameters
    metadata = env.scenario_instance.initial_state.metadata
    task_info = env.task_info()
    action_schemas = {
        operation: _json_value(env.action_schema(operation))
        for operation in sorted(env.allowed_operations)
    }
    all_instruments = instrument_contracts()
    instruments = {
        instrument_id: _json_value(all_instruments[instrument_id].to_dict())
        for instrument_id in sorted(env.allowed_instruments)
    }
    initial_constitution = env.constitution_summary()
    public_constitution_checks = tuple(
        sorted(str(item["name"]) for item in initial_constitution.get("checks", ()))
    )
    material_parameters = {
        field: _json_value(getattr(parameters, field)) for field in _MATERIAL_PARAMETER_FIELDS
    }
    public_material_catalog = task_info.get("material_catalog")
    if public_material_catalog is None:
        public_material_catalog = {
            "status": "no_public_material_choices",
            "task_id": env.task_id,
        }
    campaign_card = (
        None if env.campaign_resource_card is None else env.campaign_resource_card.to_dict()
    )
    return {
        "private_physics.constitutive_laws": {
            "domain_parameters": _json_value(parameters.domain_parameters),
            "derived_transform_id": metadata.get("derived_constitutive_transform_id"),
            "derived_calibration": _json_value(
                metadata.get("derived_constitutive_calibration")
            ),
        },
        "private_physics.initial_conditions": _initial_condition_payload(env),
        "private_physics.material_laws": {
            "parameters": material_parameters,
            "runtime_public_to_baseline_mapping": _material_mapping_payload(env),
        },
        "private_physics.randomness": {
            "world_seed": int(env.seed),
            "scenario_hidden_parameter_seed": int(
                env.scenario_instance.spec.hidden_parameter_seed
            ),
            "scenario_initial_state_seed": int(env.scenario_instance.spec.initial_state_seed),
            "observation_seed_override": env.observation_seed_override,
            "observation_noise_mode": env.observation_noise_mode,
            "observation_noise_namespace": env.observation_noise_namespace,
        },
        "private_physics.reaction_mechanism": _checkout_independent_sources(
            _json_value(env.scenario_instance.compiled_mechanism.to_dict())
        ),
        "private_physics.runtime_kernels": {
            "backend": _json_value(task_info["backend"]),
            "kernel_maturity": _json_value(env.kernel_maturity.to_dict()),
            "world_family_version": parameters.family_version,
            "constitution_rule_ids": list(constitution_rules()),
        },
        "public_contract.actions": {
            "allowed_operations": sorted(env.allowed_operations),
            "schemas": action_schemas,
        },
        "public_contract.constitution_safety": {
            "constitution_rule_ids": list(constitution_rules()),
            "initial_check_ids": list(public_constitution_checks),
            "safety_limit": float(env.safety_limit),
        },
        "public_contract.failures": {
            "transaction_status_semantics": list(PUBLIC_TRANSACTION_STATUS_SEMANTICS),
            "transaction_status_values": [
                item["status"] for item in PUBLIC_TRANSACTION_STATUS_SEMANTICS
            ],
            "rollback_on_failed_precondition": True,
            "action_preconditions": {
                operation: action_schemas[operation].get("preconditions", [])
                for operation in action_schemas
            },
            "action_constraints": {
                operation: action_schemas[operation].get("constraints", [])
                for operation in action_schemas
            },
        },
        "public_contract.instruments": {
            "allowed_instruments": sorted(env.allowed_instruments),
            "contracts": instruments,
        },
        "public_contract.material_catalog": _json_value(public_material_catalog),
        "public_contract.observations": {
            "observation_contract": _json_value(env.observation_contract.to_dict()),
            "observation_space": _json_value(
                {
                    key: {
                        "shape": list(space.shape),
                        "dtype": str(space.dtype),
                    }
                    for key, space in sorted(env.observation_space.spaces.items())
                }
            ),
            "observation_policy": env.task_spec.observation_policy,
        },
        "public_contract.resources": {
            "official_operation_budget": int(env.official_budget),
            "active_operation_budget": int(env.budget),
            "campaign_resource_card": _json_value(campaign_card),
            "instrument_costs": {
                instrument_id: {
                    "cost": instruments[instrument_id]["cost"],
                    "latency_s": instruments[instrument_id]["latency_s"],
                    "sample_consumption_L": instruments[instrument_id][
                        "sample_consumption_L"
                    ],
                }
                for instrument_id in instruments
            },
        },
        "public_contract.scoring": _json_value(env.scoring_contract.to_dict()),
        "public_contract.task": _json_value(env.task_spec.to_dict()),
    }


def extract_world_component_payloads(
    env: Any,
    *,
    inventory: WorldComponentInventory,
) -> dict[str, dict[str, Any]]:
    """Return a complete, JSON-normalized component map for a live world."""

    payloads = _component_payloads(env)
    expected = {
        component.component_id
        for component in inventory.components
        if component.layer != "identity"
    }
    if set(payloads) != expected:
        raise WorldForkRuntimeError(
            "runtime component inventory mismatch: "
            f"missing={sorted(expected - set(payloads))}, "
            f"unknown={sorted(set(payloads) - expected)}"
        )
    # Round-trip once so mappings, NumPy values, and tuples have one canonical form.
    return json.loads(json.dumps(payloads, sort_keys=True, allow_nan=False))


def _component_hashes(payloads: Mapping[str, Mapping[str, Any]]) -> dict[str, str]:
    return {
        component_id: canonical_json_sha256(payload)
        for component_id, payload in sorted(payloads.items())
    }


def _public_bundle(
    payloads: Mapping[str, Mapping[str, Any]],
    *,
    inventory: WorldComponentInventory,
) -> PublicContractBundle:
    return build_public_contract_bundle(
        {
            component_id: payload
            for component_id, payload in payloads.items()
            if component_id.startswith("public_contract.")
        },
        inventory=inventory,
    )


def _make_env(
    *,
    task_id: str,
    seed: int,
    interventions: Sequence[Mapping[str, Any]],
    noise_namespace: str,
) -> gym.Env:
    return gym.make(
        "ChemWorld",
        task_id=task_id,
        seed=seed,
        world_interventions=tuple(dict(item) for item in interventions),
        observation_seed_override=seed,
        observation_noise_mode="keyed",
        observation_noise_namespace=noise_namespace,
    )


@dataclass(frozen=True)
class BuiltWorldFork:
    """Content-addressed fork plus the two complete public bundles."""

    spec: WorldForkSpec
    parent_public_bundle: PublicContractBundle
    child_public_bundle: PublicContractBundle
    action_sequence: tuple[dict[str, Any], ...]


def build_runtime_world_fork(
    *,
    inventory: WorldComponentInventory,
    task_id: str,
    seed: int,
    intervention_class: InterventionClass,
    target_component_id: str,
    intervention_payload: Mapping[str, Any],
    noise_namespace: str = "chemworld-work-i-world-fork",
) -> BuiltWorldFork:
    """Build one real parent-child fork and certify its component diff shape."""

    parent_env = _make_env(
        task_id=task_id,
        seed=seed,
        interventions=(),
        noise_namespace=noise_namespace,
    )
    child_env = _make_env(
        task_id=task_id,
        seed=seed,
        interventions=(intervention_payload,),
        noise_namespace=noise_namespace,
    )
    try:
        parent_env.reset(seed=seed)
        child_env.reset(seed=seed)
        parent = cast(Any, parent_env.unwrapped)
        child = cast(Any, child_env.unwrapped)
        parent_payloads = extract_world_component_payloads(parent, inventory=inventory)
        child_payloads = extract_world_component_payloads(child, inventory=inventory)
        task_info = parent.task_info()
        recipe = task_recipe_from_unit_vector(
            task_info,
            np.full(task_recipe_dimension(task_info), 0.5, dtype=float),
        )
        action_sequence = tuple(_json_value(action) for action in recipe["steps"])
        spec = build_world_fork_spec(
            inventory=inventory,
            world_seed=seed,
            intervention_class=intervention_class,
            target_component_id=target_component_id,
            intervention_payload=intervention_payload,
            parent_component_sha256=_component_hashes(parent_payloads),
            child_component_sha256=_component_hashes(child_payloads),
        )
        return BuiltWorldFork(
            spec=spec,
            parent_public_bundle=_public_bundle(parent_payloads, inventory=inventory),
            child_public_bundle=_public_bundle(child_payloads, inventory=inventory),
            action_sequence=action_sequence,
        )
    finally:
        parent_env.close()
        child_env.close()


def _physical_projection(env: Any) -> dict[str, Any]:
    state = env._state.to_dict(include_hidden=True)
    return _stable_numeric_projection(
        _json_value(
            {
                "volume_L": state["volume_L"],
                "temperature_K": state["temperature_K"],
                "pressure_Pa": state["pressure_Pa"],
                "phase": state["phase"],
                "terminated": state["terminated"],
                "quenched": state["quenched"],
                "species_amounts": state["species_amounts"],
                "ledger": state["ledger"],
                "phases": state["phases"],
                "equipment": state["equipment"],
                "thermal": state["thermal"],
            }
        )
    )


def _public_observation(observation: Mapping[str, Any]) -> dict[str, Any]:
    return _json_value(observation)


def _oracle_observation(observation: Mapping[str, Any]) -> dict[str, Any]:
    """Flatten one-element observation channels for preregistered field paths."""

    normalized = _public_observation(observation)
    return {
        key: value[0] if isinstance(value, list) and len(value) == 1 else value
        for key, value in normalized.items()
    }


@dataclass(frozen=True)
class WorldForkTrace:
    """Deterministic projection of one fixed-sequence world execution."""

    task_id: str
    seed: int
    variant: str
    intervention_payload: tuple[dict[str, Any], ...]
    action_sequence: tuple[dict[str, Any], ...]
    steps: tuple[dict[str, Any], ...]
    checkpoints: dict[str, Any]

    def _core_dict(self) -> dict[str, Any]:
        return {
            "schema_version": WORLD_FORK_TRACE_SCHEMA_VERSION,
            "task_id": self.task_id,
            "seed": self.seed,
            "variant": self.variant,
            "intervention_payload": list(self.intervention_payload),
            "action_sequence": list(self.action_sequence),
            "steps": list(self.steps),
            "checkpoints": self.checkpoints,
        }

    @property
    def trace_sha256(self) -> str:
        return canonical_json_sha256(self._core_dict())

    @property
    def all_actions_committed(self) -> bool:
        return all(step["transaction_status"] == "committed" for step in self.steps)

    def to_dict(self) -> dict[str, Any]:
        return {
            **self._core_dict(),
            "trace_sha256": self.trace_sha256,
            "action_count": len(self.action_sequence),
            "committed_action_count": sum(
                step["transaction_status"] == "committed" for step in self.steps
            ),
            "all_actions_committed": self.all_actions_committed,
        }


def execute_world_trace(
    *,
    task_id: str,
    seed: int,
    variant: str,
    intervention_payload: Sequence[Mapping[str, Any]],
    action_sequence: Sequence[Mapping[str, Any]],
    noise_namespace: str = "chemworld-work-i-world-fork",
) -> WorldForkTrace:
    """Execute a frozen action sequence and retain aligned audit checkpoints."""

    if variant not in {"parent", "child"}:
        raise WorldForkRuntimeError("variant must be parent or child")
    env = _make_env(
        task_id=task_id,
        seed=seed,
        interventions=intervention_payload,
        noise_namespace=noise_namespace,
    )
    normalized_actions = tuple(_json_value(action) for action in action_sequence)
    steps: list[dict[str, Any]] = []
    terminal_physical: dict[str, Any] | None = None
    final_public: dict[str, Any] | None = None
    try:
        env.reset(seed=seed)
        raw_env = env.unwrapped
        for index, action in enumerate(normalized_actions):
            observation, reward, terminated, truncated, info = env.step(deepcopy(action))
            operation = str(action["operation"])
            if operation == "terminate":
                terminal_physical = _physical_projection(raw_env)
            if operation == "measure" and action.get("instrument") == "final_assay":
                final_public = _oracle_observation(observation)
            steps.append(
                {
                    "step_index": index,
                    "operation": operation,
                    "action_sha256": canonical_json_sha256(action),
                    "observation": _public_observation(observation),
                    "reward": float(reward),
                    "terminated": bool(terminated),
                    "truncated": bool(truncated),
                    "transaction_status": str(info.get("transaction_status", "missing")),
                }
            )
        if terminal_physical is None:
            raise WorldForkRuntimeError("qualification sequence did not reach terminate")
        if final_public is None:
            raise WorldForkRuntimeError("qualification sequence did not reach final_assay")
        return WorldForkTrace(
            task_id=task_id,
            seed=seed,
            variant=variant,
            intervention_payload=tuple(_json_value(item) for item in intervention_payload),
            action_sequence=normalized_actions,
            steps=tuple(steps),
            checkpoints={
                "terminal_assay": {
                    "physical_state": terminal_physical,
                    "public_observation": final_public,
                }
            },
        )
    finally:
        env.close()


def run_runtime_world_fork(
    *,
    inventory: WorldComponentInventory,
    task_id: str,
    seed: int,
    intervention_class: InterventionClass,
    target_component_id: str,
    intervention_payload: Mapping[str, Any],
    noise_namespace: str = "chemworld-work-i-world-fork",
) -> dict[str, Any]:
    """Build, execute, and exactly replay one parent-child fork pair."""

    built = build_runtime_world_fork(
        inventory=inventory,
        task_id=task_id,
        seed=seed,
        intervention_class=intervention_class,
        target_component_id=target_component_id,
        intervention_payload=intervention_payload,
        noise_namespace=noise_namespace,
    )
    traces: dict[str, WorldForkTrace] = {}
    replays: dict[str, WorldForkTrace] = {}
    for variant, interventions in (
        ("parent", ()),
        ("child", (dict(intervention_payload),)),
    ):
        traces[variant] = execute_world_trace(
            task_id=task_id,
            seed=seed,
            variant=variant,
            intervention_payload=interventions,
            action_sequence=built.action_sequence,
            noise_namespace=noise_namespace,
        )
        replays[variant] = execute_world_trace(
            task_id=task_id,
            seed=seed,
            variant=variant,
            intervention_payload=interventions,
            action_sequence=built.action_sequence,
            noise_namespace=noise_namespace,
        )
    replay_matches = {
        variant: traces[variant].trace_sha256 == replays[variant].trace_sha256
        for variant in traces
    }
    execution_passed = all(trace.all_actions_committed for trace in traces.values())
    return {
        "schema_version": WORLD_FORK_RUNTIME_SCHEMA_VERSION,
        "task_id": task_id,
        "seed": seed,
        "fork_spec": built.spec.to_dict(),
        "parent_public_bundle": built.parent_public_bundle.to_dict(),
        "child_public_bundle": built.child_public_bundle.to_dict(),
        "traces": {variant: trace.to_dict() for variant, trace in traces.items()},
        "replays": {variant: trace.to_dict() for variant, trace in replays.items()},
        "execution": {
            "same_action_sequence": (
                traces["parent"].action_sequence == traces["child"].action_sequence
            ),
            "parent_all_actions_committed": traces["parent"].all_actions_committed,
            "child_all_actions_committed": traces["child"].all_actions_committed,
            "passed": execution_passed,
        },
        "exact_replay": {
            "variant_matches": replay_matches,
            "passed": all(replay_matches.values()),
        },
        "provider_call_count": 0,
    }


def load_world_fork_qualification_config(path: str | Path) -> dict[str, Any]:
    """Load the runtime protocol as finite JSON without silently filling fields."""

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise WorldForkRuntimeError("qualification config must be a JSON object")
    return payload


__all__ = [
    "PUBLIC_TRANSACTION_STATUS_SEMANTICS",
    "WORLD_FORK_RUNTIME_SCHEMA_VERSION",
    "WORLD_FORK_TRACE_SCHEMA_VERSION",
    "BuiltWorldFork",
    "WorldForkRuntimeError",
    "WorldForkTrace",
    "build_runtime_world_fork",
    "execute_world_trace",
    "extract_world_component_payloads",
    "load_world_fork_qualification_config",
    "run_runtime_world_fork",
]
