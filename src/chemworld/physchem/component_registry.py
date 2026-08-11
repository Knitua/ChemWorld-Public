"""Versioned, auditable component identity registry."""

from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
from typing import Any

from chemworld.physchem.specs import (
    ComponentSpec,
    component_alias_index,
    normalize_component_token,
)

COMPONENT_REGISTRY_SCHEMA_VERSION = "chemworld-component-registry-0.1"


@dataclass(frozen=True)
class ComponentIdentityRegistry:
    """Immutable component registry with collision-safe identity lookup."""

    registry_id: str
    version: str
    components: tuple[ComponentSpec, ...]
    provenance_id: str

    def __post_init__(self) -> None:
        if not self.registry_id or not self.version or not self.provenance_id:
            raise ValueError("registry id, version, and provenance cannot be empty")
        if not self.components:
            raise ValueError("component registry cannot be empty")
        components = tuple(self.components)
        identifiers = [normalize_component_token(item.identifier) for item in components]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("duplicate component identifiers are not allowed")
        component_alias_index(components)
        object.__setattr__(self, "components", components)

    @property
    def identity_index(self) -> dict[str, str]:
        return component_alias_index(self.components)

    @property
    def digest(self) -> str:
        payload = self.to_dict(include_digest=False)
        encoded = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
        return sha256(encoded).hexdigest()

    def resolve(self, identity: str) -> ComponentSpec:
        token = normalize_component_token(identity)
        try:
            identifier = self.identity_index[token]
        except KeyError as exc:
            raise KeyError(f"unknown component identity {identity!r}") from exc
        return next(item for item in self.components if item.identifier == identifier)

    def to_dict(self, *, include_digest: bool = True) -> dict[str, object]:
        payload: dict[str, object] = {
            "schema_version": COMPONENT_REGISTRY_SCHEMA_VERSION,
            "registry_id": self.registry_id,
            "version": self.version,
            "provenance_id": self.provenance_id,
            "components": [component.to_dict() for component in self.components],
        }
        if include_digest:
            payload["digest"] = self.digest
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> ComponentIdentityRegistry:
        schema_version = str(payload.get("schema_version", ""))
        if schema_version != COMPONENT_REGISTRY_SCHEMA_VERSION:
            raise ValueError(f"unsupported component registry schema {schema_version!r}")
        registry = cls(
            registry_id=str(payload["registry_id"]),
            version=str(payload["version"]),
            provenance_id=str(payload["provenance_id"]),
            components=tuple(ComponentSpec.from_dict(dict(item)) for item in payload["components"]),
        )
        expected_digest = payload.get("digest")
        if expected_digest is not None and str(expected_digest) != registry.digest:
            raise ValueError("component registry digest mismatch")
        return registry


def curated_component_registry() -> ComponentIdentityRegistry:
    """Return the small reference-checked ChemWorld component registry."""

    from chemworld.physchem.curated_properties import curated_components

    return ComponentIdentityRegistry(
        registry_id="chemworld-curated-components",
        version="1.0.0",
        components=curated_components(),
        provenance_id="chemworld-curated-properties-v1",
    )


__all__ = [
    "COMPONENT_REGISTRY_SCHEMA_VERSION",
    "ComponentIdentityRegistry",
    "curated_component_registry",
]
