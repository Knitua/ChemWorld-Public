"""Content-addressed parent-child specifications for Work I world forks.

The specification records what changed, not how a world is executed.  Fork
builders and runners are deliberately downstream so a lineage record can be
validated without importing the environment or invoking a provider.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, cast

from chemworld.foundation.world_fork_manifest import (
    ALLOWED_INTERVENTION_CLASSES,
    InterventionClass,
    WorldComponentInventory,
    canonical_json_sha256,
)

WORLD_FORK_SPEC_SCHEMA_VERSION = "chemworld-world-fork-spec-0.1"
WORLD_FORK_ID_PREFIX = "chemworld-work-i-fork"
DERIVED_IDENTITY_FIELDS = ("world_sha256", "lineage_sha256")

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SNAPSHOT_KEYS = frozenset({"world_sha256", "lineage_sha256", "component_sha256"})
_DIFF_KEYS = frozenset(
    {"changed_component_ids", "invariant_component_ids", "derived_identity_fields"}
)
_SPEC_KEYS = frozenset(
    {
        "schema_version",
        "fork_id",
        "inventory_id",
        "inventory_sha256",
        "world_seed",
        "intervention_class",
        "target_component_id",
        "intervention_payload",
        "intervention_sha256",
        "parent",
        "child",
        "component_diff",
    }
)


class WorldForkSpecError(ValueError):
    """Raised when a fork specification is not an admissible single-target fork."""


def _require_exact_keys(payload: Mapping[str, Any], expected: frozenset[str], label: str) -> None:
    actual = set(payload)
    if actual != expected:
        raise WorldForkSpecError(
            f"{label} fields do not match schema: missing={sorted(expected - actual)}, "
            f"unknown={sorted(actual - expected)}"
        )


def _require_sha256(value: str, label: str) -> None:
    if not _SHA256.fullmatch(value):
        raise WorldForkSpecError(f"{label} must be a lowercase SHA-256 digest")


def _string_tuple(value: Any, label: str, *, nonempty: bool = True) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise WorldForkSpecError(f"{label} must be a list of non-empty strings")
    result = tuple(value)
    if nonempty and not result:
        raise WorldForkSpecError(f"{label} must not be empty")
    if len(result) != len(set(result)):
        raise WorldForkSpecError(f"{label} must not contain duplicates")
    return result


def _world_component_ids(inventory: WorldComponentInventory) -> tuple[str, ...]:
    return tuple(
        sorted(
            component.component_id
            for component in inventory.components
            if component.layer != "identity"
        )
    )


def _normalize_component_digests(
    values: Mapping[str, str],
    *,
    inventory: WorldComponentInventory,
    label: str,
) -> dict[str, str]:
    expected = set(_world_component_ids(inventory))
    actual = set(values)
    if actual != expected:
        raise WorldForkSpecError(
            f"{label} component set mismatch: missing={sorted(expected - actual)}, "
            f"unknown={sorted(actual - expected)}"
        )
    normalized = {str(key): str(value) for key, value in sorted(values.items())}
    for component_id, digest in normalized.items():
        _require_sha256(digest, f"{label}.{component_id}")
    return normalized


def world_snapshot_sha256(
    component_sha256: Mapping[str, str],
    *,
    inventory_sha256: str,
) -> str:
    """Hash one complete non-identity world definition."""

    _require_sha256(inventory_sha256, "inventory_sha256")
    if not component_sha256:
        raise WorldForkSpecError("component_sha256 must not be empty")
    for component_id, digest in component_sha256.items():
        if not isinstance(component_id, str) or not component_id:
            raise WorldForkSpecError("component_sha256 keys must be non-empty strings")
        if not isinstance(digest, str):
            raise WorldForkSpecError(f"component digest for {component_id} must be a string")
        _require_sha256(digest, f"component_sha256.{component_id}")
    return canonical_json_sha256(
        {
            "schema_version": "chemworld-world-snapshot-digest-0.1",
            "inventory_sha256": inventory_sha256,
            "component_sha256": dict(sorted(component_sha256.items())),
        }
    )


def root_lineage_sha256(*, inventory_sha256: str, world_sha256: str) -> str:
    """Derive the auditable root lineage identity for a base world."""

    _require_sha256(inventory_sha256, "inventory_sha256")
    _require_sha256(world_sha256, "world_sha256")
    return canonical_json_sha256(
        {
            "schema_version": "chemworld-world-lineage-root-0.1",
            "inventory_sha256": inventory_sha256,
            "world_sha256": world_sha256,
        }
    )


def child_lineage_sha256(
    *,
    inventory_sha256: str,
    parent_world_sha256: str,
    parent_lineage_sha256: str,
    child_world_sha256: str,
    intervention_sha256: str,
    target_component_id: str,
) -> str:
    """Derive a child lineage from the complete parent and intervention identity."""

    for label, value in (
        ("inventory_sha256", inventory_sha256),
        ("parent_world_sha256", parent_world_sha256),
        ("parent_lineage_sha256", parent_lineage_sha256),
        ("child_world_sha256", child_world_sha256),
        ("intervention_sha256", intervention_sha256),
    ):
        _require_sha256(value, label)
    return canonical_json_sha256(
        {
            "schema_version": "chemworld-world-lineage-edge-0.1",
            "inventory_sha256": inventory_sha256,
            "parent_world_sha256": parent_world_sha256,
            "parent_lineage_sha256": parent_lineage_sha256,
            "child_world_sha256": child_world_sha256,
            "intervention_sha256": intervention_sha256,
            "target_component_id": target_component_id,
        }
    )


@dataclass(frozen=True)
class WorldSnapshotDigest:
    """Content identity for one world and its position in a lineage."""

    world_sha256: str
    lineage_sha256: str
    component_sha256: dict[str, str]

    @classmethod
    def from_dict(
        cls,
        payload: Mapping[str, Any],
        *,
        inventory: WorldComponentInventory,
        label: str,
    ) -> WorldSnapshotDigest:
        _require_exact_keys(payload, _SNAPSHOT_KEYS, label)
        raw_components = payload["component_sha256"]
        if not isinstance(raw_components, Mapping) or not all(
            isinstance(key, str) and isinstance(value, str) for key, value in raw_components.items()
        ):
            raise WorldForkSpecError(f"{label}.component_sha256 must be a string map")
        snapshot = cls(
            world_sha256=str(payload["world_sha256"]),
            lineage_sha256=str(payload["lineage_sha256"]),
            component_sha256=_normalize_component_digests(
                cast(Mapping[str, str], raw_components),
                inventory=inventory,
                label=label,
            ),
        )
        _require_sha256(snapshot.world_sha256, f"{label}.world_sha256")
        _require_sha256(snapshot.lineage_sha256, f"{label}.lineage_sha256")
        expected_world = world_snapshot_sha256(
            snapshot.component_sha256,
            inventory_sha256=inventory.content_sha256,
        )
        if snapshot.world_sha256 != expected_world:
            raise WorldForkSpecError(f"{label}.world_sha256 does not bind its components")
        return snapshot

    def to_dict(self) -> dict[str, Any]:
        return {
            "world_sha256": self.world_sha256,
            "lineage_sha256": self.lineage_sha256,
            "component_sha256": dict(sorted(self.component_sha256.items())),
        }


@dataclass(frozen=True)
class WorldComponentDiff:
    """Exact causal and invariant component partition for one fork edge."""

    changed_component_ids: tuple[str, ...]
    invariant_component_ids: tuple[str, ...]
    derived_identity_fields: tuple[str, ...]

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> WorldComponentDiff:
        _require_exact_keys(payload, _DIFF_KEYS, "component_diff")
        return cls(
            changed_component_ids=_string_tuple(
                payload["changed_component_ids"], "changed_component_ids"
            ),
            invariant_component_ids=_string_tuple(
                payload["invariant_component_ids"], "invariant_component_ids"
            ),
            derived_identity_fields=_string_tuple(
                payload["derived_identity_fields"], "derived_identity_fields"
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "changed_component_ids": list(self.changed_component_ids),
            "invariant_component_ids": list(self.invariant_component_ids),
            "derived_identity_fields": list(self.derived_identity_fields),
        }


@dataclass(frozen=True)
class WorldForkSpec:
    """A validated, single-private-component fork from a content-addressed parent."""

    schema_version: str
    fork_id: str
    inventory_id: str
    inventory_sha256: str
    world_seed: int
    intervention_class: InterventionClass
    target_component_id: str
    intervention_payload: dict[str, Any]
    intervention_sha256: str
    parent: WorldSnapshotDigest
    child: WorldSnapshotDigest
    component_diff: WorldComponentDiff

    @classmethod
    def from_dict(
        cls,
        payload: Mapping[str, Any],
        *,
        inventory: WorldComponentInventory,
    ) -> WorldForkSpec:
        _require_exact_keys(payload, _SPEC_KEYS, "world_fork_spec")
        raw_intervention = payload["intervention_payload"]
        raw_parent = payload["parent"]
        raw_child = payload["child"]
        raw_diff = payload["component_diff"]
        if not isinstance(raw_intervention, Mapping) or not raw_intervention:
            raise WorldForkSpecError("intervention_payload must be a non-empty object")
        if not isinstance(raw_parent, Mapping) or not isinstance(raw_child, Mapping):
            raise WorldForkSpecError("parent and child must be objects")
        if not isinstance(raw_diff, Mapping):
            raise WorldForkSpecError("component_diff must be an object")
        intervention_class = str(payload["intervention_class"])
        spec = cls(
            schema_version=str(payload["schema_version"]),
            fork_id=str(payload["fork_id"]),
            inventory_id=str(payload["inventory_id"]),
            inventory_sha256=str(payload["inventory_sha256"]),
            world_seed=payload["world_seed"],
            intervention_class=cast(InterventionClass, intervention_class),
            target_component_id=str(payload["target_component_id"]),
            intervention_payload=dict(raw_intervention),
            intervention_sha256=str(payload["intervention_sha256"]),
            parent=WorldSnapshotDigest.from_dict(raw_parent, inventory=inventory, label="parent"),
            child=WorldSnapshotDigest.from_dict(raw_child, inventory=inventory, label="child"),
            component_diff=WorldComponentDiff.from_dict(raw_diff),
        )
        spec.validate(inventory)
        return spec

    def validate(self, inventory: WorldComponentInventory) -> None:
        if self.schema_version != WORLD_FORK_SPEC_SCHEMA_VERSION:
            raise WorldForkSpecError("unsupported world-fork specification schema")
        if self.inventory_id != inventory.inventory_id:
            raise WorldForkSpecError("fork inventory_id does not match the supplied inventory")
        if self.inventory_sha256 != inventory.content_sha256:
            raise WorldForkSpecError("fork inventory_sha256 does not match the frozen inventory")
        if isinstance(self.world_seed, bool) or not isinstance(self.world_seed, int):
            raise WorldForkSpecError("world_seed must be a non-negative integer")
        if self.world_seed < 0:
            raise WorldForkSpecError("world_seed must be a non-negative integer")
        if self.intervention_class not in ALLOWED_INTERVENTION_CLASSES:
            raise WorldForkSpecError("unsupported intervention_class")
        target = inventory.component_by_id.get(self.target_component_id)
        if target is None or target.fork_policy != "intervention_target":
            raise WorldForkSpecError("target_component_id is not an intervention target")
        if self.intervention_class not in target.allowed_intervention_classes:
            raise WorldForkSpecError("intervention class is incompatible with target component")
        _require_sha256(self.inventory_sha256, "inventory_sha256")
        _require_sha256(self.intervention_sha256, "intervention_sha256")
        expected_intervention = canonical_json_sha256(self.intervention_payload)
        if self.intervention_sha256 != expected_intervention:
            raise WorldForkSpecError("intervention_sha256 does not bind intervention_payload")
        expected_child_lineage = child_lineage_sha256(
            inventory_sha256=self.inventory_sha256,
            parent_world_sha256=self.parent.world_sha256,
            parent_lineage_sha256=self.parent.lineage_sha256,
            child_world_sha256=self.child.world_sha256,
            intervention_sha256=self.intervention_sha256,
            target_component_id=self.target_component_id,
        )
        if self.child.lineage_sha256 != expected_child_lineage:
            raise WorldForkSpecError("child lineage does not bind parent, child, and intervention")
        expected_fork_id = f"{WORLD_FORK_ID_PREFIX}-{expected_child_lineage[:16]}"
        if self.fork_id != expected_fork_id:
            raise WorldForkSpecError("fork_id does not match child lineage")
        changed = tuple(
            sorted(
                component_id
                for component_id in self.parent.component_sha256
                if self.parent.component_sha256[component_id]
                != self.child.component_sha256[component_id]
            )
        )
        expected_changed = (self.target_component_id,)
        if changed != expected_changed:
            raise WorldForkSpecError(
                f"fork must change exactly its declared target: observed={changed}"
            )
        invariant = tuple(
            component_id
            for component_id in _world_component_ids(inventory)
            if component_id != self.target_component_id
        )
        if self.component_diff.changed_component_ids != expected_changed:
            raise WorldForkSpecError("component_diff changed set is not the declared target")
        if self.component_diff.invariant_component_ids != invariant:
            raise WorldForkSpecError("component_diff invariant set is incomplete or unordered")
        if self.component_diff.derived_identity_fields != DERIVED_IDENTITY_FIELDS:
            raise WorldForkSpecError("component_diff derived identity fields are not frozen")
        if self.parent.world_sha256 == self.child.world_sha256:
            raise WorldForkSpecError("parent and child world identities must differ")
        if self.parent.lineage_sha256 == self.child.lineage_sha256:
            raise WorldForkSpecError("parent and child lineage identities must differ")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "fork_id": self.fork_id,
            "inventory_id": self.inventory_id,
            "inventory_sha256": self.inventory_sha256,
            "world_seed": self.world_seed,
            "intervention_class": self.intervention_class,
            "target_component_id": self.target_component_id,
            "intervention_payload": self.intervention_payload,
            "intervention_sha256": self.intervention_sha256,
            "parent": self.parent.to_dict(),
            "child": self.child.to_dict(),
            "component_diff": self.component_diff.to_dict(),
        }

    @property
    def content_sha256(self) -> str:
        return canonical_json_sha256(self.to_dict())


def build_world_fork_spec(
    *,
    inventory: WorldComponentInventory,
    world_seed: int,
    intervention_class: InterventionClass,
    target_component_id: str,
    intervention_payload: Mapping[str, Any],
    parent_component_sha256: Mapping[str, str],
    child_component_sha256: Mapping[str, str],
    parent_lineage_sha256: str | None = None,
) -> WorldForkSpec:
    """Build and validate a content-addressed fork specification."""

    parent_components = _normalize_component_digests(
        parent_component_sha256,
        inventory=inventory,
        label="parent",
    )
    child_components = _normalize_component_digests(
        child_component_sha256,
        inventory=inventory,
        label="child",
    )
    inventory_sha256 = inventory.content_sha256
    parent_world = world_snapshot_sha256(
        parent_components,
        inventory_sha256=inventory_sha256,
    )
    child_world = world_snapshot_sha256(
        child_components,
        inventory_sha256=inventory_sha256,
    )
    parent_lineage = parent_lineage_sha256 or root_lineage_sha256(
        inventory_sha256=inventory_sha256,
        world_sha256=parent_world,
    )
    _require_sha256(parent_lineage, "parent_lineage_sha256")
    intervention = dict(intervention_payload)
    if not intervention:
        raise WorldForkSpecError("intervention_payload must be a non-empty object")
    intervention_sha256 = canonical_json_sha256(intervention)
    child_lineage = child_lineage_sha256(
        inventory_sha256=inventory_sha256,
        parent_world_sha256=parent_world,
        parent_lineage_sha256=parent_lineage,
        child_world_sha256=child_world,
        intervention_sha256=intervention_sha256,
        target_component_id=target_component_id,
    )
    invariant_components = tuple(
        component_id
        for component_id in _world_component_ids(inventory)
        if component_id != target_component_id
    )
    spec = WorldForkSpec(
        schema_version=WORLD_FORK_SPEC_SCHEMA_VERSION,
        fork_id=f"{WORLD_FORK_ID_PREFIX}-{child_lineage[:16]}",
        inventory_id=inventory.inventory_id,
        inventory_sha256=inventory_sha256,
        world_seed=world_seed,
        intervention_class=intervention_class,
        target_component_id=target_component_id,
        intervention_payload=intervention,
        intervention_sha256=intervention_sha256,
        parent=WorldSnapshotDigest(parent_world, parent_lineage, parent_components),
        child=WorldSnapshotDigest(child_world, child_lineage, child_components),
        component_diff=WorldComponentDiff(
            changed_component_ids=(target_component_id,),
            invariant_component_ids=invariant_components,
            derived_identity_fields=DERIVED_IDENTITY_FIELDS,
        ),
    )
    spec.validate(inventory)
    return spec


def audit_world_fork_spec(
    spec: WorldForkSpec,
    *,
    inventory: WorldComponentInventory,
) -> dict[str, Any]:
    """Return a deterministic, publication-facing audit of one fork edge."""

    spec.validate(inventory)
    public_contract_ids = tuple(
        sorted(
            component.component_id
            for component in inventory.components
            if component.layer == "public_contract"
        )
    )
    public_contract_invariant = all(
        spec.parent.component_sha256[component_id] == spec.child.component_sha256[component_id]
        for component_id in public_contract_ids
    )
    return {
        "report_version": "chemworld-world-fork-spec-audit-0.1",
        "passed": public_contract_invariant,
        "fork_id": spec.fork_id,
        "fork_spec_sha256": spec.content_sha256,
        "inventory_id": inventory.inventory_id,
        "inventory_sha256": inventory.content_sha256,
        "world_seed": spec.world_seed,
        "intervention_class": spec.intervention_class,
        "target_component_id": spec.target_component_id,
        "parent_world_sha256": spec.parent.world_sha256,
        "parent_lineage_sha256": spec.parent.lineage_sha256,
        "child_world_sha256": spec.child.world_sha256,
        "child_lineage_sha256": spec.child.lineage_sha256,
        "component_diff": spec.component_diff.to_dict(),
        "public_contract_invariant": public_contract_invariant,
        "public_contract_component_count": len(public_contract_ids),
        "claim_boundary": {
            "single_private_physics_target": True,
            "execution_claim": False,
            "divergence_claim": False,
            "agent_performance_claim": False,
        },
    }


__all__ = [
    "DERIVED_IDENTITY_FIELDS",
    "WORLD_FORK_ID_PREFIX",
    "WORLD_FORK_SPEC_SCHEMA_VERSION",
    "WorldComponentDiff",
    "WorldForkSpec",
    "WorldForkSpecError",
    "WorldSnapshotDigest",
    "audit_world_fork_spec",
    "build_world_fork_spec",
    "child_lineage_sha256",
    "root_lineage_sha256",
    "world_snapshot_sha256",
]
