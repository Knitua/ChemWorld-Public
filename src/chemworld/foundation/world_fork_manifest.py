"""Frozen component vocabulary for auditable Work I world forks.

This module defines the boundary between a world intervention and a benchmark
contract change.  It intentionally does not build or execute forks; later
world-fork code consumes this inventory as its source of truth.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast

WORLD_COMPONENT_INVENTORY_SCHEMA_VERSION = "chemworld-world-component-inventory-0.1"
WORLD_COMPONENT_INVENTORY_ID = "chemworld-work-i-world-components-v0.1"

ComponentLayer = Literal["identity", "private_physics", "public_contract"]
ComponentVisibility = Literal["private", "public", "audit_only"]
ForkPolicy = Literal["invariant", "intervention_target", "derived"]
InterventionClass = Literal[
    "mechanism_or_constitutive_law",
    "material_law_counterfactual",
]

ALLOWED_LAYERS = frozenset({"identity", "private_physics", "public_contract"})
ALLOWED_VISIBILITIES = frozenset({"private", "public", "audit_only"})
ALLOWED_FORK_POLICIES = frozenset({"invariant", "intervention_target", "derived"})
ALLOWED_INTERVENTION_CLASSES = (
    "mechanism_or_constitutive_law",
    "material_law_counterfactual",
)

WORK_I_V01_REQUIRED_COMPONENT_IDS = frozenset(
    {
        "identity.lineage",
        "identity.world",
        "private_physics.constitutive_laws",
        "private_physics.initial_conditions",
        "private_physics.material_laws",
        "private_physics.randomness",
        "private_physics.reaction_mechanism",
        "private_physics.runtime_kernels",
        "public_contract.actions",
        "public_contract.constitution_safety",
        "public_contract.failures",
        "public_contract.instruments",
        "public_contract.material_catalog",
        "public_contract.observations",
        "public_contract.resources",
        "public_contract.scoring",
        "public_contract.task",
    }
)
WORK_I_V01_REQUIRED_RULE_IDS = frozenset(
    {
        "audit_identity_non_disclosure",
        "fixed_execution_substrate",
        "matched_initialization_and_randomness",
        "public_interface_invariance",
        "single_private_physics_target",
    }
)

_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_.-]*$")
_COMPONENT_KEYS = frozenset(
    {
        "component_id",
        "layer",
        "visibility",
        "fork_policy",
        "allowed_intervention_classes",
        "canonical_payload_sources",
        "implementation_anchors",
        "description",
    }
)
_RULE_KEYS = frozenset({"rule_id", "component_ids", "requirement"})
_SCOPE_KEYS = frozenset(
    {
        "paper",
        "certificate",
        "intervention_classes",
        "base_fork_pairs",
        "single_declared_target_per_fork",
        "public_contract_must_be_invariant",
        "provider_calls_required",
        "agent_performance_claim_allowed",
    }
)
_INVENTORY_KEYS = frozenset(
    {
        "schema_version",
        "inventory_id",
        "status",
        "scope",
        "components",
        "cross_component_rules",
    }
)


class WorldComponentManifestError(ValueError):
    """Raised when a world-component manifest violates the frozen schema."""


def _require_exact_keys(payload: Mapping[str, Any], expected: frozenset[str], label: str) -> None:
    actual = set(payload)
    if actual != expected:
        raise WorldComponentManifestError(
            f"{label} fields do not match schema: missing={sorted(expected - actual)}, "
            f"unknown={sorted(actual - expected)}"
        )


def _require_identifier(value: str, label: str) -> None:
    if not _IDENTIFIER.fullmatch(value):
        raise WorldComponentManifestError(f"{label} must be a lowercase stable identifier")


def _string_tuple(value: Any, label: str, *, nonempty: bool = True) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise WorldComponentManifestError(f"{label} must be a list of non-empty strings")
    result = tuple(value)
    if nonempty and not result:
        raise WorldComponentManifestError(f"{label} must not be empty")
    if len(result) != len(set(result)):
        raise WorldComponentManifestError(f"{label} must not contain duplicates")
    return result


@dataclass(frozen=True)
class WorldComponentSpec:
    """One canonical component of an executable world definition."""

    component_id: str
    layer: ComponentLayer
    visibility: ComponentVisibility
    fork_policy: ForkPolicy
    allowed_intervention_classes: tuple[InterventionClass, ...]
    canonical_payload_sources: tuple[str, ...]
    implementation_anchors: tuple[str, ...]
    description: str

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> WorldComponentSpec:
        _require_exact_keys(payload, _COMPONENT_KEYS, "component")
        layer = str(payload["layer"])
        visibility = str(payload["visibility"])
        fork_policy = str(payload["fork_policy"])
        interventions = _string_tuple(
            payload["allowed_intervention_classes"],
            "allowed_intervention_classes",
            nonempty=False,
        )
        component = cls(
            component_id=str(payload["component_id"]),
            layer=cast(ComponentLayer, layer),
            visibility=cast(ComponentVisibility, visibility),
            fork_policy=cast(ForkPolicy, fork_policy),
            allowed_intervention_classes=cast(tuple[InterventionClass, ...], interventions),
            canonical_payload_sources=_string_tuple(
                payload["canonical_payload_sources"], "canonical_payload_sources"
            ),
            implementation_anchors=_string_tuple(
                payload["implementation_anchors"], "implementation_anchors"
            ),
            description=str(payload["description"]),
        )
        component.validate()
        return component

    def validate(self) -> None:
        _require_identifier(self.component_id, "component_id")
        if self.layer not in ALLOWED_LAYERS:
            raise WorldComponentManifestError(f"unsupported layer for {self.component_id}")
        if self.visibility not in ALLOWED_VISIBILITIES:
            raise WorldComponentManifestError(f"unsupported visibility for {self.component_id}")
        if self.fork_policy not in ALLOWED_FORK_POLICIES:
            raise WorldComponentManifestError(f"unsupported fork_policy for {self.component_id}")
        component_namespace = self.component_id.partition(".")[0]
        if component_namespace != self.layer:
            raise WorldComponentManifestError(
                f"component namespace and layer disagree for {self.component_id}"
            )
        if not self.description.strip():
            raise WorldComponentManifestError(f"description is required for {self.component_id}")
        unknown = set(self.allowed_intervention_classes) - set(ALLOWED_INTERVENTION_CLASSES)
        if unknown:
            raise WorldComponentManifestError(
                f"unsupported intervention classes for {self.component_id}: {sorted(unknown)}"
            )
        if self.fork_policy == "intervention_target":
            if self.layer != "private_physics" or self.visibility != "private":
                raise WorldComponentManifestError(
                    f"intervention target {self.component_id} must be private physics"
                )
            if not self.allowed_intervention_classes:
                raise WorldComponentManifestError(
                    f"intervention target {self.component_id} has no allowed intervention"
                )
        elif self.allowed_intervention_classes:
            raise WorldComponentManifestError(
                f"non-target {self.component_id} cannot allow interventions"
            )
        if self.layer == "public_contract" and (
            self.visibility != "public" or self.fork_policy != "invariant"
        ):
            raise WorldComponentManifestError(
                f"public contract {self.component_id} must be public and invariant"
            )
        if self.fork_policy == "derived" and (
            self.layer != "identity" or self.visibility != "audit_only"
        ):
            raise WorldComponentManifestError(
                f"derived component {self.component_id} must be audit-only identity"
            )
        for anchor in self.implementation_anchors:
            path = Path(anchor)
            if path.is_absolute() or ".." in path.parts:
                raise WorldComponentManifestError(
                    f"implementation anchor must be repository-relative: {anchor}"
                )

    def to_dict(self) -> dict[str, Any]:
        return {
            "component_id": self.component_id,
            "layer": self.layer,
            "visibility": self.visibility,
            "fork_policy": self.fork_policy,
            "allowed_intervention_classes": list(self.allowed_intervention_classes),
            "canonical_payload_sources": list(self.canonical_payload_sources),
            "implementation_anchors": list(self.implementation_anchors),
            "description": self.description,
        }


@dataclass(frozen=True)
class CrossComponentRule:
    """A declarative relation that later fork certificates must enforce."""

    rule_id: str
    component_ids: tuple[str, ...]
    requirement: str

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> CrossComponentRule:
        _require_exact_keys(payload, _RULE_KEYS, "cross_component_rule")
        rule = cls(
            rule_id=str(payload["rule_id"]),
            component_ids=_string_tuple(payload["component_ids"], "component_ids"),
            requirement=str(payload["requirement"]),
        )
        _require_identifier(rule.rule_id, "rule_id")
        if not rule.requirement.strip():
            raise WorldComponentManifestError(f"requirement is required for {rule.rule_id}")
        return rule

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "component_ids": list(self.component_ids),
            "requirement": self.requirement,
        }


@dataclass(frozen=True)
class WorldForkScope:
    """Frozen claim and execution boundary for the Work I certificate."""

    paper: str
    certificate: str
    intervention_classes: tuple[InterventionClass, ...]
    base_fork_pairs: bool
    single_declared_target_per_fork: bool
    public_contract_must_be_invariant: bool
    provider_calls_required: bool
    agent_performance_claim_allowed: bool

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> WorldForkScope:
        _require_exact_keys(payload, _SCOPE_KEYS, "scope")
        boolean_keys = _SCOPE_KEYS - {"paper", "certificate", "intervention_classes"}
        if any(type(payload[key]) is not bool for key in boolean_keys):
            raise WorldComponentManifestError("scope flags must be booleans")
        interventions = _string_tuple(payload["intervention_classes"], "intervention_classes")
        scope = cls(
            paper=str(payload["paper"]),
            certificate=str(payload["certificate"]),
            intervention_classes=cast(tuple[InterventionClass, ...], interventions),
            base_fork_pairs=bool(payload["base_fork_pairs"]),
            single_declared_target_per_fork=bool(payload["single_declared_target_per_fork"]),
            public_contract_must_be_invariant=bool(payload["public_contract_must_be_invariant"]),
            provider_calls_required=bool(payload["provider_calls_required"]),
            agent_performance_claim_allowed=bool(payload["agent_performance_claim_allowed"]),
        )
        if scope.paper != "work-i" or scope.certificate != "world-fork-programmability":
            raise WorldComponentManifestError("scope must remain bound to the Work I certificate")
        if scope.intervention_classes != ALLOWED_INTERVENTION_CLASSES:
            raise WorldComponentManifestError(
                "scope must declare the frozen Work I intervention classes in order"
            )
        if not scope.base_fork_pairs or not scope.single_declared_target_per_fork:
            raise WorldComponentManifestError("Work I requires paired, single-target forks")
        if not scope.public_contract_must_be_invariant:
            raise WorldComponentManifestError("Work I requires invariant public contracts")
        if scope.provider_calls_required or scope.agent_performance_claim_allowed:
            raise WorldComponentManifestError(
                "Work I fork certification is deterministic and makes no agent-performance claim"
            )
        return scope

    def to_dict(self) -> dict[str, Any]:
        return {
            "paper": self.paper,
            "certificate": self.certificate,
            "intervention_classes": list(self.intervention_classes),
            "base_fork_pairs": self.base_fork_pairs,
            "single_declared_target_per_fork": self.single_declared_target_per_fork,
            "public_contract_must_be_invariant": self.public_contract_must_be_invariant,
            "provider_calls_required": self.provider_calls_required,
            "agent_performance_claim_allowed": self.agent_performance_claim_allowed,
        }


@dataclass(frozen=True)
class WorldComponentInventory:
    """Strict, content-addressed inventory consumed by world-fork tooling."""

    schema_version: str
    inventory_id: str
    status: str
    scope: WorldForkScope
    components: tuple[WorldComponentSpec, ...]
    cross_component_rules: tuple[CrossComponentRule, ...]

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> WorldComponentInventory:
        _require_exact_keys(payload, _INVENTORY_KEYS, "inventory")
        raw_scope = payload["scope"]
        raw_components = payload["components"]
        raw_rules = payload["cross_component_rules"]
        if not isinstance(raw_scope, Mapping):
            raise WorldComponentManifestError("scope must be an object")
        if not isinstance(raw_components, list) or not all(
            isinstance(item, Mapping) for item in raw_components
        ):
            raise WorldComponentManifestError("components must be a list of objects")
        if not isinstance(raw_rules, list) or not all(
            isinstance(item, Mapping) for item in raw_rules
        ):
            raise WorldComponentManifestError("cross_component_rules must be a list of objects")
        inventory = cls(
            schema_version=str(payload["schema_version"]),
            inventory_id=str(payload["inventory_id"]),
            status=str(payload["status"]),
            scope=WorldForkScope.from_dict(raw_scope),
            components=tuple(WorldComponentSpec.from_dict(item) for item in raw_components),
            cross_component_rules=tuple(CrossComponentRule.from_dict(item) for item in raw_rules),
        )
        inventory.validate()
        return inventory

    def validate(self) -> None:
        if self.schema_version != WORLD_COMPONENT_INVENTORY_SCHEMA_VERSION:
            raise WorldComponentManifestError("unsupported world-component inventory schema")
        if self.inventory_id != WORLD_COMPONENT_INVENTORY_ID or self.status != "frozen":
            raise WorldComponentManifestError("Work I inventory identity and status must be frozen")
        component_ids = tuple(component.component_id for component in self.components)
        if len(component_ids) != len(set(component_ids)):
            raise WorldComponentManifestError("component_id values must be unique")
        if set(component_ids) != WORK_I_V01_REQUIRED_COMPONENT_IDS:
            raise WorldComponentManifestError(
                "Work I v0.1 component set mismatch: "
                f"missing={sorted(WORK_I_V01_REQUIRED_COMPONENT_IDS - set(component_ids))}, "
                f"unknown={sorted(set(component_ids) - WORK_I_V01_REQUIRED_COMPONENT_IDS)}"
            )
        rule_ids = tuple(rule.rule_id for rule in self.cross_component_rules)
        if len(rule_ids) != len(set(rule_ids)):
            raise WorldComponentManifestError("rule_id values must be unique")
        if set(rule_ids) != WORK_I_V01_REQUIRED_RULE_IDS:
            raise WorldComponentManifestError(
                "Work I v0.1 rule set mismatch: "
                f"missing={sorted(WORK_I_V01_REQUIRED_RULE_IDS - set(rule_ids))}, "
                f"unknown={sorted(set(rule_ids) - WORK_I_V01_REQUIRED_RULE_IDS)}"
            )
        unknown_rule_components = {
            component_id
            for rule in self.cross_component_rules
            for component_id in rule.component_ids
            if component_id not in set(component_ids)
        }
        if unknown_rule_components:
            raise WorldComponentManifestError(
                f"rules reference unknown components: {sorted(unknown_rule_components)}"
            )
        target_map = self.intervention_target_map
        if set(target_map) != set(ALLOWED_INTERVENTION_CLASSES):
            raise WorldComponentManifestError("each Work I intervention class needs a target")
        expected_targets = {
            "mechanism_or_constitutive_law": (
                "private_physics.constitutive_laws",
                "private_physics.reaction_mechanism",
            ),
            "material_law_counterfactual": ("private_physics.material_laws",),
        }
        if target_map != expected_targets:
            raise WorldComponentManifestError(
                f"Work I v0.1 intervention target map changed: {target_map}"
            )

    @property
    def component_by_id(self) -> dict[str, WorldComponentSpec]:
        return {component.component_id: component for component in self.components}

    @property
    def intervention_target_map(self) -> dict[str, tuple[str, ...]]:
        return {
            intervention: tuple(
                sorted(
                    component.component_id
                    for component in self.components
                    if intervention in component.allowed_intervention_classes
                )
            )
            for intervention in ALLOWED_INTERVENTION_CLASSES
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "inventory_id": self.inventory_id,
            "status": self.status,
            "scope": self.scope.to_dict(),
            "components": [component.to_dict() for component in self.components],
            "cross_component_rules": [rule.to_dict() for rule in self.cross_component_rules],
        }

    @property
    def content_sha256(self) -> str:
        return canonical_json_sha256(self.to_dict())


def canonical_json_sha256(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def load_world_component_inventory(path: str | Path) -> WorldComponentInventory:
    """Load and validate one frozen inventory without mutating repository state."""

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise WorldComponentManifestError("inventory root must be an object")
    return WorldComponentInventory.from_dict(payload)


def audit_world_component_inventory(
    inventory: WorldComponentInventory,
    *,
    repository_root: str | Path,
) -> dict[str, Any]:
    """Build a deterministic audit report for the frozen inventory."""

    root = Path(repository_root)
    anchors = sorted(
        {
            anchor
            for component in inventory.components
            for anchor in component.implementation_anchors
        }
    )
    missing_anchors = [anchor for anchor in anchors if not (root / anchor).is_file()]
    policy_counts = {
        policy: sum(component.fork_policy == policy for component in inventory.components)
        for policy in sorted(ALLOWED_FORK_POLICIES)
    }
    layer_counts = {
        layer: sum(component.layer == layer for component in inventory.components)
        for layer in sorted(ALLOWED_LAYERS)
    }
    public_contract_ids = sorted(
        component.component_id
        for component in inventory.components
        if component.layer == "public_contract"
    )
    passed = not missing_anchors
    return {
        "report_version": "chemworld-world-component-inventory-audit-0.1",
        "inventory_id": inventory.inventory_id,
        "inventory_schema_version": inventory.schema_version,
        "inventory_sha256": inventory.content_sha256,
        "passed": passed,
        "summary": {
            "component_count": len(inventory.components),
            "cross_component_rule_count": len(inventory.cross_component_rules),
            "implementation_anchor_count": len(anchors),
            "missing_implementation_anchor_count": len(missing_anchors),
            "layer_counts": layer_counts,
            "fork_policy_counts": policy_counts,
        },
        "intervention_target_map": {
            key: list(value) for key, value in inventory.intervention_target_map.items()
        },
        "public_contract_component_ids": public_contract_ids,
        "implementation_anchor_audit": {
            "anchors": anchors,
            "missing": missing_anchors,
        },
        "claim_boundary": {
            "certificate": inventory.scope.certificate,
            "provider_calls_required": inventory.scope.provider_calls_required,
            "agent_performance_claim_allowed": inventory.scope.agent_performance_claim_allowed,
        },
    }


def world_component_manifest_schema() -> dict[str, Any]:
    """Return the machine-readable structural schema for the v0.1 manifest."""

    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": WORLD_COMPONENT_INVENTORY_SCHEMA_VERSION,
        "type": "object",
        "additionalProperties": False,
        "required": sorted(_INVENTORY_KEYS),
        "properties": {
            "schema_version": {"const": WORLD_COMPONENT_INVENTORY_SCHEMA_VERSION},
            "inventory_id": {"const": WORLD_COMPONENT_INVENTORY_ID},
            "status": {"const": "frozen"},
            "scope": {
                "type": "object",
                "additionalProperties": False,
                "required": sorted(_SCOPE_KEYS),
                "properties": {
                    "paper": {"const": "work-i"},
                    "certificate": {"const": "world-fork-programmability"},
                    "intervention_classes": {
                        "type": "array",
                        "prefixItems": [
                            {"const": "mechanism_or_constitutive_law"},
                            {"const": "material_law_counterfactual"},
                        ],
                        "minItems": 2,
                        "maxItems": 2,
                    },
                    "base_fork_pairs": {"const": True},
                    "single_declared_target_per_fork": {"const": True},
                    "public_contract_must_be_invariant": {"const": True},
                    "provider_calls_required": {"const": False},
                    "agent_performance_claim_allowed": {"const": False},
                },
            },
            "components": {
                "type": "array",
                "minItems": len(WORK_I_V01_REQUIRED_COMPONENT_IDS),
                "maxItems": len(WORK_I_V01_REQUIRED_COMPONENT_IDS),
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": sorted(_COMPONENT_KEYS),
                    "properties": {
                        "component_id": {
                            "type": "string",
                            "pattern": _IDENTIFIER.pattern,
                        },
                        "layer": {"enum": sorted(ALLOWED_LAYERS)},
                        "visibility": {"enum": sorted(ALLOWED_VISIBILITIES)},
                        "fork_policy": {"enum": sorted(ALLOWED_FORK_POLICIES)},
                        "allowed_intervention_classes": {
                            "type": "array",
                            "items": {"enum": list(ALLOWED_INTERVENTION_CLASSES)},
                            "uniqueItems": True,
                        },
                        "canonical_payload_sources": {
                            "type": "array",
                            "items": {"type": "string", "minLength": 1},
                            "minItems": 1,
                            "uniqueItems": True,
                        },
                        "implementation_anchors": {
                            "type": "array",
                            "items": {"type": "string", "minLength": 1},
                            "minItems": 1,
                            "uniqueItems": True,
                        },
                        "description": {"type": "string", "minLength": 1},
                    },
                },
            },
            "cross_component_rules": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": sorted(_RULE_KEYS),
                    "properties": {
                        "rule_id": {"type": "string", "pattern": _IDENTIFIER.pattern},
                        "component_ids": {
                            "type": "array",
                            "items": {"type": "string", "minLength": 1},
                            "minItems": 1,
                            "uniqueItems": True,
                        },
                        "requirement": {"type": "string", "minLength": 1},
                    },
                },
            },
        },
    }


__all__ = [
    "ALLOWED_INTERVENTION_CLASSES",
    "WORK_I_V01_REQUIRED_COMPONENT_IDS",
    "WORK_I_V01_REQUIRED_RULE_IDS",
    "WORLD_COMPONENT_INVENTORY_ID",
    "WORLD_COMPONENT_INVENTORY_SCHEMA_VERSION",
    "CrossComponentRule",
    "WorldComponentInventory",
    "WorldComponentManifestError",
    "WorldComponentSpec",
    "WorldForkScope",
    "audit_world_component_inventory",
    "canonical_json_sha256",
    "load_world_component_inventory",
    "world_component_manifest_schema",
]
