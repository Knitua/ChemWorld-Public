"""Executable candidate controls for public semantic invariance."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

from chemworld.action_codec import ActionCodec
from chemworld.agents.task_recipes import (
    task_recipe_dimension,
    task_recipe_from_unit_vector,
)
from chemworld.envs.chemworld_env import ChemWorldEnv
from chemworld.tasks import SERIOUS_TASK_IDS

PROTOCOL_SCHEMA_VERSION = "chemworld-semantic-invariance-protocol-0.1"
REPORT_SCHEMA_VERSION = "chemworld-semantic-invariance-audit-0.1"
REQUIRED_PROBES = (
    "action_key_order",
    "material_code_remap",
    "observation_field_reorder",
    "equivalent_action_sequence",
    "format_perturbation",
)
PUBLIC_INFO_KEYS = (
    "step",
    "remaining_budget",
    "experiment_index",
    "operation_id",
    "experiment_ended",
    "operation_type",
    "preconditions",
    "constraint_flags",
    "observed_keys",
    "observed_mask",
    "state_delta_summary",
    "reward_source",
)


def _canonical_sha256(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _validate_permutation(values: tuple[int, ...], name: str) -> None:
    if not values or sorted(values) != list(range(len(values))):
        raise ValueError(f"{name} must be a permutation of [0, n)")


def _integer_code(value: Any, *, size: int, field: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field} material code must be an integer")
    try:
        numeric = float(np.asarray(value).reshape(-1)[0])
    except (TypeError, ValueError, IndexError) as error:
        raise ValueError(f"{field} material code must be an integer") from error
    index = int(numeric)
    if not np.isfinite(numeric) or float(index) != numeric:
        raise ValueError(f"{field} material code must be an integer")
    if not 0 <= index < size:
        raise ValueError(f"{field} material code {value!r} is outside [0, {size - 1}]")
    return index


@dataclass(frozen=True)
class MaterialCodeRemap:
    """Reversible public-code permutation that leaves physical identities fixed."""

    solvent_public_to_canonical: tuple[int, ...]
    catalyst_public_to_canonical: tuple[int, ...]

    def __post_init__(self) -> None:
        _validate_permutation(self.solvent_public_to_canonical, "solvent_public_to_canonical")
        _validate_permutation(
            self.catalyst_public_to_canonical,
            "catalyst_public_to_canonical",
        )

    def _permutation(self, field: str) -> tuple[int, ...]:
        if field in {"solvent", "extractant"}:
            return self.solvent_public_to_canonical
        if field == "catalyst":
            return self.catalyst_public_to_canonical
        raise ValueError(f"unsupported material field {field!r}")

    def encode_action(self, canonical_action: Mapping[str, Any]) -> dict[str, Any]:
        """Encode canonical material indices as public opaque indices."""

        encoded = dict(canonical_action)
        for field in ("solvent", "extractant", "catalyst"):
            if field not in encoded:
                continue
            permutation = self._permutation(field)
            canonical = _integer_code(encoded[field], size=len(permutation), field=field)
            encoded[field] = permutation.index(canonical)
        return encoded

    def decode_action(self, public_action: Mapping[str, Any]) -> dict[str, Any]:
        """Decode public opaque indices or reject invalid mappings."""

        decoded = dict(public_action)
        for field in ("solvent", "extractant", "catalyst"):
            if field not in decoded:
                continue
            permutation = self._permutation(field)
            public = _integer_code(decoded[field], size=len(permutation), field=field)
            decoded[field] = permutation[public]
        return decoded

    def opaque_catalog(self, catalog: Mapping[str, Any]) -> dict[str, Any]:
        """Return an identity-neutral public catalog aligned with the remapped codes."""

        def remap_group(
            group: str,
            permutation: tuple[int, ...],
        ) -> list[dict[str, Any]] | None:
            entries = catalog.get(group)
            if entries is None:
                return None
            if not isinstance(entries, list) or len(entries) != len(permutation):
                raise ValueError(f"material catalog {group!r} does not match permutation")
            return [
                {
                    "index": public_index,
                    "public_code": f"{group[:-1]}_{public_index:03d}",
                    "identity_kind": "opaque_semantic_invariance_code",
                }
                for public_index in range(len(permutation))
            ]

        opaque: dict[str, Any] = {
            "catalog_version": "chemworld-public-material-remap-candidate-0.1",
            "mapping_visibility_policy": "public codes only; canonical mapping remains private",
        }
        for group, permutation in (
            ("solvents", self.solvent_public_to_canonical),
            ("catalysts", self.catalyst_public_to_canonical),
        ):
            remapped = remap_group(group, permutation)
            if remapped is not None:
                opaque[group] = remapped
        if not any(group in opaque for group in ("solvents", "catalysts")):
            raise ValueError("material catalog has no remappable material group")
        return opaque


def nested_equivalent_action(action: Mapping[str, Any]) -> dict[str, Any]:
    """Represent one flat action as a nested payload with reversed key order."""

    if "operation" not in action:
        raise ValueError("equivalent action requires operation")
    payload = {key: value for key, value in reversed(tuple(action.items())) if key != "operation"}
    return {"payload": payload, "operation": action["operation"]}


def reordered_observation(observation: Mapping[str, Any]) -> dict[str, Any]:
    """Return the same keyed observation in reverse insertion order."""

    return dict(reversed(tuple(observation.items())))


def _values_close(left: Any, right: Any, *, atol: float, rtol: float) -> bool:
    if isinstance(left, Mapping) and isinstance(right, Mapping):
        return set(left) == set(right) and all(
            _values_close(left[key], right[key], atol=atol, rtol=rtol) for key in left
        )
    if (
        isinstance(left, Sequence)
        and isinstance(right, Sequence)
        and not isinstance(left, (str, bytes))
        and not isinstance(right, (str, bytes))
    ):
        return len(left) == len(right) and all(
            _values_close(a, b, atol=atol, rtol=rtol) for a, b in zip(left, right, strict=True)
        )
    if isinstance(left, (int, float, np.number, np.ndarray)) or isinstance(
        right, (int, float, np.number, np.ndarray)
    ):
        try:
            left_array = np.asarray(left, dtype=float)
            right_array = np.asarray(right, dtype=float)
        except (TypeError, ValueError):
            return False
        return left_array.shape == right_array.shape and bool(
            np.allclose(left_array, right_array, atol=atol, rtol=rtol, equal_nan=True)
        )
    return left == right


def _maximum_numeric_delta(left: Any, right: Any) -> float:
    try:
        left_array = np.asarray(left, dtype=float)
        right_array = np.asarray(right, dtype=float)
    except (TypeError, ValueError):
        return 0.0
    if left_array.shape != right_array.shape:
        return float("inf")
    finite = np.isfinite(left_array) & np.isfinite(right_array)
    if not np.any(finite):
        return 0.0
    return float(np.max(np.abs(left_array[finite] - right_array[finite])))


def _observation_delta(left: Mapping[str, Any], right: Mapping[str, Any]) -> float:
    if set(left) != set(right):
        return float("inf")
    return max((_maximum_numeric_delta(left[key], right[key]) for key in left), default=0.0)


def _info_projection(info: Mapping[str, Any]) -> dict[str, Any]:
    return {key: info.get(key) for key in PUBLIC_INFO_KEYS}


def _material_remap(protocol: Mapping[str, Any]) -> MaterialCodeRemap:
    mapping = protocol.get("material_code_remap")
    if not isinstance(mapping, Mapping):
        raise ValueError("protocol requires material_code_remap")
    solvent = mapping.get("solvent_public_to_canonical")
    catalyst = mapping.get("catalyst_public_to_canonical")
    if not isinstance(solvent, list) or not isinstance(catalyst, list):
        raise ValueError("material code permutations must be lists")
    if not all(isinstance(value, int) and not isinstance(value, bool) for value in solvent):
        raise ValueError("solvent material code permutation must contain integers")
    if not all(isinstance(value, int) and not isinstance(value, bool) for value in catalyst):
        raise ValueError("catalyst material code permutation must contain integers")
    return MaterialCodeRemap(tuple(solvent), tuple(catalyst))


def _paired_task_run(
    task_id: str,
    seed: int,
    *,
    coordinate: float,
    remap: MaterialCodeRemap,
    atol: float,
    rtol: float,
) -> dict[str, Any]:
    baseline_env = ChemWorldEnv(task_id=task_id, seed=seed)
    variant_env = ChemWorldEnv(task_id=task_id, seed=seed)
    baseline_observation, task_info = baseline_env.reset(seed=seed)
    variant_observation, variant_task_info = variant_env.reset(seed=seed)
    dimension = task_recipe_dimension(task_info)
    recipe = task_recipe_from_unit_vector(
        task_info,
        np.full(dimension, coordinate, dtype=float),
    )
    steps = recipe["steps"]
    if not isinstance(steps, list) or not steps:
        raise ValueError(f"task {task_id} produced no recipe steps")

    opaque_catalog = remap.opaque_catalog(variant_task_info["material_catalog"])
    canonical_ids = {
        str(entry["canonical_id"])
        for group in ("solvents", "catalysts")
        for entry in variant_task_info["material_catalog"].get(group, [])
        if "canonical_id" in entry
    }
    opaque_text = json.dumps(opaque_catalog, sort_keys=True)
    catalog_opaque = all(canonical_id not in opaque_text for canonical_id in canonical_ids)
    observations_equal = _values_close(
        baseline_observation,
        reordered_observation(variant_observation),
        atol=atol,
        rtol=rtol,
    )
    action_key_order_equal = True
    material_roundtrip_equal = True
    equivalent_sequence_equal = True
    format_perturbation_equal = True
    rewards_equal = True
    termination_equal = True
    public_info_equal = True
    max_observation_delta = _observation_delta(
        baseline_observation,
        variant_observation,
    )
    max_reward_delta = 0.0
    codec = ActionCodec()

    for raw_action in steps:
        canonical = codec.canonicalize(dict(raw_action))
        reversed_action = dict(reversed(tuple(canonical.items())))
        action_key_order_equal &= codec.canonicalize(reversed_action) == canonical

        public_action = remap.encode_action(canonical)
        material_roundtrip_equal &= remap.decode_action(public_action) == canonical
        nested = nested_equivalent_action(public_action)
        pretty = json.dumps(nested, indent=2, ensure_ascii=False)
        compact = json.dumps(nested, sort_keys=True, separators=(",", ":"))
        pretty_public = codec.canonicalize(json.loads(pretty))
        compact_public = codec.canonicalize(json.loads(compact))
        format_perturbation_equal &= pretty_public == compact_public
        variant_canonical = codec.canonicalize(remap.decode_action(pretty_public))
        equivalent_sequence_equal &= variant_canonical == canonical

        baseline_step = baseline_env.step(canonical)
        variant_step = variant_env.step(variant_canonical)
        (
            baseline_observation,
            baseline_reward,
            baseline_terminated,
            baseline_truncated,
            baseline_info,
        ) = baseline_step
        (
            variant_observation,
            variant_reward,
            variant_terminated,
            variant_truncated,
            variant_info,
        ) = variant_step
        reordered = reordered_observation(variant_observation)
        observations_equal &= _values_close(
            baseline_observation,
            reordered,
            atol=atol,
            rtol=rtol,
        )
        rewards_equal &= bool(np.isclose(baseline_reward, variant_reward, atol=atol, rtol=rtol))
        termination_equal &= (baseline_terminated, baseline_truncated) == (
            variant_terminated,
            variant_truncated,
        )
        public_info_equal &= _values_close(
            _info_projection(baseline_info),
            _info_projection(variant_info),
            atol=atol,
            rtol=rtol,
        )
        max_observation_delta = max(
            max_observation_delta,
            _observation_delta(baseline_observation, variant_observation),
        )
        max_reward_delta = max(
            max_reward_delta,
            abs(float(baseline_reward) - float(variant_reward)),
        )

    probes = {
        "action_key_order": action_key_order_equal,
        "material_code_remap": material_roundtrip_equal and catalog_opaque,
        "observation_field_reorder": observations_equal,
        "equivalent_action_sequence": equivalent_sequence_equal
        and rewards_equal
        and termination_equal
        and public_info_equal,
        "format_perturbation": format_perturbation_equal,
    }
    return {
        "task_id": task_id,
        "seed": seed,
        "recipe_coordinate": coordinate,
        "step_count": len(steps),
        "probes": probes,
        "catalog_opaque": catalog_opaque,
        "max_observation_delta": max_observation_delta,
        "max_reward_delta": max_reward_delta,
        "rewards_equal": rewards_equal,
        "termination_equal": termination_equal,
        "public_info_equal": public_info_equal,
        "passed": all(probes.values()),
    }


def audit_semantic_invariance(protocol: Mapping[str, Any]) -> dict[str, Any]:
    """Run paired public-boundary invariance controls for every serious task."""

    raw_task_ids = protocol.get("task_ids")
    raw_seeds = protocol.get("seeds")
    raw_tolerance = protocol.get("tolerance")
    raw_probes = protocol.get("probes")
    task_ids = (
        [task_id for task_id in raw_task_ids if isinstance(task_id, str)]
        if isinstance(raw_task_ids, list)
        else []
    )
    seeds = (
        [seed for seed in raw_seeds if isinstance(seed, int) and not isinstance(seed, bool)]
        if isinstance(raw_seeds, list)
        else []
    )
    tolerance: Mapping[str, Any] = raw_tolerance if isinstance(raw_tolerance, Mapping) else {}
    probes: Mapping[str, Any] = raw_probes if isinstance(raw_probes, Mapping) else {}
    schema_valid = protocol.get("schema_version") == PROTOCOL_SCHEMA_VERSION
    status_valid = protocol.get("status") == "candidate_non_claiming"
    task_scope_valid = (
        isinstance(raw_task_ids, list)
        and len(task_ids) == len(raw_task_ids)
        and task_ids == list(SERIOUS_TASK_IDS)
    )
    seed_scope_valid = isinstance(raw_seeds, list) and len(seeds) == len(raw_seeds) and bool(seeds)
    tolerance_valid = isinstance(raw_tolerance, Mapping) and all(
        isinstance(tolerance.get(key), (int, float))
        and not isinstance(tolerance.get(key), bool)
        and np.isfinite(float(tolerance[key]))
        and float(tolerance[key]) >= 0.0
        for key in ("atol", "rtol")
    )
    probes_valid = (
        isinstance(raw_probes, Mapping)
        and set(probes) == set(REQUIRED_PROBES)
        and all(probes.get(probe) == "executable" for probe in REQUIRED_PROBES)
    )
    raw_coordinate = protocol.get("recipe_coordinate", 0.5)
    coordinate_valid = (
        isinstance(raw_coordinate, (int, float))
        and not isinstance(raw_coordinate, bool)
        and np.isfinite(float(raw_coordinate))
        and 0.0 <= float(raw_coordinate) <= 1.0
    )
    coordinate = float(raw_coordinate) if coordinate_valid else 0.5

    run_reports: list[dict[str, Any]] = []
    configuration_error: str | None = None
    invalid_code_fail_closed = False
    if all(
        (
            schema_valid,
            status_valid,
            task_scope_valid,
            seed_scope_valid,
            tolerance_valid,
            probes_valid,
            coordinate_valid,
        )
    ):
        try:
            remap = _material_remap(protocol)
            try:
                remap.decode_action({"operation": "add_solvent", "solvent": 99})
            except ValueError:
                invalid_code_fail_closed = True
            for task_id in task_ids:
                for seed in seeds:
                    run_reports.append(
                        _paired_task_run(
                            task_id,
                            seed,
                            coordinate=coordinate,
                            remap=remap,
                            atol=float(tolerance["atol"]),
                            rtol=float(tolerance["rtol"]),
                        )
                    )
        except (KeyError, TypeError, ValueError) as error:
            configuration_error = str(error)

    all_runs_pass = bool(run_reports) and all(report["passed"] for report in run_reports)
    expected_run_count = len(SERIOUS_TASK_IDS) * len(seeds) if seed_scope_valid else 0
    run_count_complete = len(run_reports) == expected_run_count
    checks = {
        "schema": schema_valid,
        "candidate_is_non_claiming": status_valid,
        "task_scope": task_scope_valid,
        "seed_scope": seed_scope_valid,
        "paired_tolerance": tolerance_valid,
        "probe_contract": probes_valid,
        "recipe_coordinate": coordinate_valid,
        "invalid_material_code_fail_closed": invalid_code_fail_closed,
        "paired_run_count": run_count_complete,
        "all_paired_runs_pass": all_runs_pass,
    }
    controls_ready = all(checks.values()) and configuration_error is None
    task_reports = {
        task_id: {
            "paired_run_count": sum(report["task_id"] == task_id for report in run_reports),
            "seeds": [report["seed"] for report in run_reports if report["task_id"] == task_id],
            "step_counts": [
                report["step_count"] for report in run_reports if report["task_id"] == task_id
            ],
            "max_observation_delta": max(
                (
                    report["max_observation_delta"]
                    for report in run_reports
                    if report["task_id"] == task_id
                ),
                default=None,
            ),
            "max_reward_delta": max(
                (
                    report["max_reward_delta"]
                    for report in run_reports
                    if report["task_id"] == task_id
                ),
                default=None,
            ),
            "probes": {
                probe: all(
                    report["probes"][probe]
                    for report in run_reports
                    if report["task_id"] == task_id
                )
                for probe in REQUIRED_PROBES
            },
            "passed": all(
                report["passed"] for report in run_reports if report["task_id"] == task_id
            )
            and any(report["task_id"] == task_id for report in run_reports),
        }
        for task_id in SERIOUS_TASK_IDS
    }
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "protocol_id": protocol.get("protocol_id"),
        "protocol_sha256": _canonical_sha256(protocol),
        "status": (
            "semantic_invariance_controls_ready"
            if controls_ready
            else "semantic_invariance_controls_blocked"
        ),
        "controls_ready": controls_ready,
        "benchmark_claim_allowed": False,
        "publication_ready": False,
        "checks": checks,
        "configuration_error": configuration_error,
        "paired_run_count": len(run_reports),
        "tasks": task_reports,
        "limitations": [
            (
                "The material probe validates a reversible opaque boundary-code adapter; "
                "it does not claim that exchanging physical material identities leaves "
                "chemistry unchanged."
            ),
            (
                "The paired controls use deterministic median recipes and two declared "
                "seeds, not formal method comparisons."
            ),
            (
                "The controls validate representation invariance only and do not "
                "authorize or overwrite an evaluation result."
            ),
            (
                "Public harness isolation and the expanded exploit matrix remain "
                "separate release gates."
            ),
        ],
        "remaining_release_gates": [
            "bind the controls to the frozen vNext public harness and method protocol",
            "run paired formal methods under the frozen Train/Dev/Bench world-family splits",
            "complete public-harness leakage and exploit audits",
        ],
    }


__all__ = [
    "PROTOCOL_SCHEMA_VERSION",
    "REPORT_SCHEMA_VERSION",
    "REQUIRED_PROBES",
    "MaterialCodeRemap",
    "audit_semantic_invariance",
    "nested_equivalent_action",
    "reordered_observation",
]
