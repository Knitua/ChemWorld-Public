"""Integrated audit for executable Work I world forks."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

from chemworld.foundation.world_fork_divergence import (
    DivergenceOracleSpec,
    evaluate_divergence_oracle,
)
from chemworld.foundation.world_fork_manifest import (
    WorldComponentInventory,
    canonical_json_sha256,
)
from chemworld.foundation.world_fork_public_contract import (
    PublicContractBundle,
    certify_public_contract_invariance,
)
from chemworld.foundation.world_fork_spec import WorldForkSpec, audit_world_fork_spec

WORLD_FORK_AUDIT_REPORT_VERSION = "chemworld-world-fork-runtime-audit-0.1"


class WorldForkAuditError(ValueError):
    """Raised when a runtime result cannot be bound to its audit objects."""


_TRACE_CORE_KEYS = (
    "schema_version",
    "task_id",
    "seed",
    "variant",
    "intervention_payload",
    "action_sequence",
    "steps",
    "checkpoints",
)


def _trace_digest(trace: Mapping[str, Any]) -> str:
    try:
        core = {key: trace[key] for key in _TRACE_CORE_KEYS}
    except KeyError as exc:
        raise WorldForkAuditError(f"trace is missing {exc.args[0]}") from exc
    return canonical_json_sha256(core)


def _runtime_execution_and_replay(runtime_result: Mapping[str, Any]) -> tuple[dict, dict]:
    traces = runtime_result.get("traces")
    replays = runtime_result.get("replays")
    if not isinstance(traces, Mapping) or not isinstance(replays, Mapping):
        raise WorldForkAuditError("runtime result lacks traces or replays")
    variants = ("parent", "child")
    if any(
        not isinstance(group.get(variant), Mapping)
        for group in (traces, replays)
        for variant in variants
    ):
        raise WorldForkAuditError("runtime result lacks a parent or child trace")
    trace_hash_bound: dict[str, bool] = {}
    replay_hash_bound: dict[str, bool] = {}
    replay_matches: dict[str, bool] = {}
    for variant in variants:
        trace = traces[variant]
        replay = replays[variant]
        trace_digest = _trace_digest(trace)
        replay_digest = _trace_digest(replay)
        trace_hash_bound[variant] = trace.get("trace_sha256") == trace_digest
        replay_hash_bound[variant] = replay.get("trace_sha256") == replay_digest
        replay_matches[variant] = trace_digest == replay_digest
    action_sequences_equal = (
        traces["parent"].get("action_sequence")
        == traces["child"].get("action_sequence")
    )
    committed = {
        variant: all(
            step.get("transaction_status") == "committed"
            for step in traces[variant].get("steps", ())
        )
        for variant in variants
    }
    execution = {
        "same_action_sequence": action_sequences_equal,
        "parent_all_actions_committed": committed["parent"],
        "child_all_actions_committed": committed["child"],
        "passed": action_sequences_equal and all(committed.values()),
    }
    replay = {
        "trace_hash_bound": trace_hash_bound,
        "replay_hash_bound": replay_hash_bound,
        "variant_matches": replay_matches,
        "passed": all(trace_hash_bound.values())
        and all(replay_hash_bound.values())
        and all(replay_matches.values()),
    }
    return execution, replay


def audit_runtime_world_fork(
    runtime_result: Mapping[str, Any],
    *,
    inventory: WorldComponentInventory,
    oracle: DivergenceOracleSpec,
) -> dict[str, Any]:
    """Bind lineage, public invariance, response divergence, and replay gates."""

    spec_payload = runtime_result.get("fork_spec")
    parent_bundle_payload = runtime_result.get("parent_public_bundle")
    child_bundle_payload = runtime_result.get("child_public_bundle")
    traces = runtime_result.get("traces")
    if not all(
        isinstance(item, Mapping)
        for item in (spec_payload, parent_bundle_payload, child_bundle_payload, traces)
    ):
        raise WorldForkAuditError("runtime result is missing required audit objects")
    spec_mapping = cast(Mapping[str, Any], spec_payload)
    parent_bundle_mapping = cast(Mapping[str, Any], parent_bundle_payload)
    child_bundle_mapping = cast(Mapping[str, Any], child_bundle_payload)
    trace_mapping = cast(Mapping[str, Any], traces)
    spec = WorldForkSpec.from_dict(spec_mapping, inventory=inventory)
    parent_bundle = PublicContractBundle.from_dict(
        parent_bundle_mapping,
        inventory=inventory,
    )
    child_bundle = PublicContractBundle.from_dict(
        child_bundle_mapping,
        inventory=inventory,
    )
    lineage_audit = audit_world_fork_spec(spec, inventory=inventory)
    public_certificate = certify_public_contract_invariance(
        spec=spec,
        inventory=inventory,
        parent_bundle=parent_bundle,
        child_bundle=child_bundle,
    ).to_dict()
    try:
        parent_checkpoints = trace_mapping["parent"]["checkpoints"]
        child_checkpoints = trace_mapping["child"]["checkpoints"]
    except (KeyError, TypeError) as exc:
        raise WorldForkAuditError("runtime traces lack aligned checkpoints") from exc
    divergence = evaluate_divergence_oracle(
        oracle=oracle,
        spec=spec,
        inventory=inventory,
        parent_checkpoints=parent_checkpoints,
        child_checkpoints=child_checkpoints,
    )
    execution, replay = _runtime_execution_and_replay(runtime_result)
    gates = {
        "single_target_lineage": bool(lineage_audit["passed"]),
        "public_contract_invariance": bool(public_certificate["passed"]),
        "same_sequence_executability": bool(execution.get("passed")),
        "expected_response_divergence": bool(divergence["passed"]),
        "exact_replay": bool(replay.get("passed")),
        "zero_provider_calls": runtime_result.get("provider_call_count") == 0,
    }
    return {
        "report_version": WORLD_FORK_AUDIT_REPORT_VERSION,
        "fork_id": spec.fork_id,
        "fork_spec_sha256": spec.content_sha256,
        "task_id": runtime_result.get("task_id"),
        "seed": runtime_result.get("seed"),
        "intervention_class": spec.intervention_class,
        "target_component_id": spec.target_component_id,
        "gates": gates,
        "passed": all(gates.values()),
        "lineage_audit": lineage_audit,
        "public_contract_certificate": public_certificate,
        "divergence_evaluation": divergence,
        "execution_audit": execution,
        "exact_replay_audit": replay,
        "claim_boundary": {
            "programmable_single_component_world_fork": True,
            "public_interface_invariance": True,
            "fixed_sequence_executability": True,
            "expected_physical_and_observation_divergence": True,
            "exact_replay": True,
            "agent_performance_claim": False,
            "physical_laboratory_transfer_claim": False,
        },
    }


__all__ = [
    "WORLD_FORK_AUDIT_REPORT_VERSION",
    "WorldForkAuditError",
    "audit_runtime_world_fork",
]
