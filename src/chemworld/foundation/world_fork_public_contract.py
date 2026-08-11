"""Public-contract bundles and invariance certificates for Work I world forks."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from chemworld.foundation.world_fork_manifest import (
    WorldComponentInventory,
    canonical_json_sha256,
)
from chemworld.foundation.world_fork_spec import WorldForkSpec

PUBLIC_CONTRACT_BUNDLE_SCHEMA_VERSION = "chemworld-public-contract-bundle-0.1"
PUBLIC_CONTRACT_CERTIFICATE_VERSION = "chemworld-public-contract-invariance-0.1"

_BUNDLE_KEYS = frozenset({"schema_version", "component_payloads"})
_FORBIDDEN_IDENTITY_KEYS = frozenset(
    {
        "child_lineage_sha256",
        "child_world_sha256",
        "fork_id",
        "fork_identity",
        "intervention_sha256",
        "inventory_sha256",
        "lineage_sha256",
        "material_law_counterfactual_hash",
        "mechanism_family_intervention_hash",
        "parent_lineage_sha256",
        "parent_world_sha256",
        "target_component_id",
        "world_family_intervention_hash",
        "world_id",
        "world_provider",
    }
)


class PublicContractCertificateError(ValueError):
    """Raised when a public-contract bundle is malformed or out of scope."""


def _public_component_ids(inventory: WorldComponentInventory) -> tuple[str, ...]:
    return tuple(
        sorted(
            component.component_id
            for component in inventory.components
            if component.layer == "public_contract"
        )
    )


def _json_normalize(value: Any, label: str) -> Any:
    try:
        encoded = json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError) as exc:
        raise PublicContractCertificateError(f"{label} must be finite JSON data") from exc
    return json.loads(encoded)


@dataclass(frozen=True)
class PublicContractBundle:
    """Canonical public payloads for all F01 public-contract components."""

    component_payloads: dict[str, Any]

    @classmethod
    def from_dict(
        cls,
        payload: Mapping[str, Any],
        *,
        inventory: WorldComponentInventory,
    ) -> PublicContractBundle:
        actual_keys = set(payload)
        if actual_keys != _BUNDLE_KEYS:
            raise PublicContractCertificateError(
                "public-contract bundle fields do not match schema: "
                f"missing={sorted(_BUNDLE_KEYS - actual_keys)}, "
                f"unknown={sorted(actual_keys - _BUNDLE_KEYS)}"
            )
        if payload["schema_version"] != PUBLIC_CONTRACT_BUNDLE_SCHEMA_VERSION:
            raise PublicContractCertificateError("unsupported public-contract bundle schema")
        raw_components = payload["component_payloads"]
        if not isinstance(raw_components, Mapping):
            raise PublicContractCertificateError("component_payloads must be an object")
        return build_public_contract_bundle(raw_components, inventory=inventory)

    @property
    def component_sha256(self) -> dict[str, str]:
        return {
            component_id: canonical_json_sha256(payload)
            for component_id, payload in self.component_payloads.items()
        }

    @property
    def content_sha256(self) -> str:
        return canonical_json_sha256(self.to_dict())

    @property
    def bundle_id(self) -> str:
        return f"chemworld-public-contract-{self.content_sha256[:16]}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": PUBLIC_CONTRACT_BUNDLE_SCHEMA_VERSION,
            "component_payloads": self.component_payloads,
        }


@dataclass(frozen=True)
class PublicIdentityLeakageFinding:
    """One audit-only identity key or exact value found in public data."""

    component_id: str
    path: str
    finding_kind: str
    matched_value: str

    def to_dict(self) -> dict[str, str]:
        return {
            "component_id": self.component_id,
            "path": self.path,
            "finding_kind": self.finding_kind,
            "matched_value": self.matched_value,
        }


@dataclass(frozen=True)
class PublicContractComponentResult:
    """Parent-child equality and WorldForkSpec binding for one public component."""

    component_id: str
    parent_payload_sha256: str
    child_payload_sha256: str
    payloads_equal: bool
    parent_spec_bound: bool
    child_spec_bound: bool

    @property
    def passed(self) -> bool:
        return self.payloads_equal and self.parent_spec_bound and self.child_spec_bound

    def to_dict(self) -> dict[str, Any]:
        return {
            "component_id": self.component_id,
            "parent_payload_sha256": self.parent_payload_sha256,
            "child_payload_sha256": self.child_payload_sha256,
            "payloads_equal": self.payloads_equal,
            "parent_spec_bound": self.parent_spec_bound,
            "child_spec_bound": self.child_spec_bound,
            "passed": self.passed,
        }


@dataclass(frozen=True)
class PublicContractInvarianceCertificate:
    """A deterministic proof object for the complete public fork interface."""

    fork_id: str
    fork_spec_sha256: str
    inventory_id: str
    inventory_sha256: str
    parent_bundle_sha256: str
    child_bundle_sha256: str
    component_results: tuple[PublicContractComponentResult, ...]
    leakage_findings: tuple[PublicIdentityLeakageFinding, ...]

    @property
    def passed(self) -> bool:
        return all(result.passed for result in self.component_results) and not (
            self.leakage_findings
        )

    @property
    def certificate_id(self) -> str:
        payload = self._core_dict()
        return f"chemworld-public-invariance-{canonical_json_sha256(payload)[:16]}"

    def _core_dict(self) -> dict[str, Any]:
        return {
            "certificate_version": PUBLIC_CONTRACT_CERTIFICATE_VERSION,
            "fork_id": self.fork_id,
            "fork_spec_sha256": self.fork_spec_sha256,
            "inventory_id": self.inventory_id,
            "inventory_sha256": self.inventory_sha256,
            "parent_bundle_sha256": self.parent_bundle_sha256,
            "child_bundle_sha256": self.child_bundle_sha256,
            "component_results": [result.to_dict() for result in self.component_results],
            "leakage_findings": [finding.to_dict() for finding in self.leakage_findings],
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            **self._core_dict(),
            "certificate_id": self.certificate_id,
            "public_component_count": len(self.component_results),
            "invariant_component_count": sum(
                result.payloads_equal for result in self.component_results
            ),
            "spec_bound_component_count": sum(
                result.parent_spec_bound and result.child_spec_bound
                for result in self.component_results
            ),
            "identity_leakage_finding_count": len(self.leakage_findings),
            "passed": self.passed,
            "claim_boundary": {
                "public_interface_invariance": True,
                "fork_identity_non_disclosure": True,
                "physical_divergence_claim": False,
                "replay_claim": False,
                "agent_performance_claim": False,
            },
        }


def build_public_contract_bundle(
    component_payloads: Mapping[str, Any],
    *,
    inventory: WorldComponentInventory,
) -> PublicContractBundle:
    """Validate, deep-normalize, and order all nine public component payloads."""

    expected = set(_public_component_ids(inventory))
    actual = set(component_payloads)
    if actual != expected:
        raise PublicContractCertificateError(
            "public component set mismatch: "
            f"missing={sorted(expected - actual)}, unknown={sorted(actual - expected)}"
        )
    normalized = {
        component_id: _json_normalize(component_payloads[component_id], component_id)
        for component_id in sorted(expected)
    }
    return PublicContractBundle(component_payloads=normalized)


def _forbidden_exact_values(spec: WorldForkSpec) -> frozenset[str]:
    return frozenset(
        {
            spec.fork_id,
            spec.intervention_sha256,
            spec.inventory_sha256,
            spec.parent.world_sha256,
            spec.parent.lineage_sha256,
            spec.child.world_sha256,
            spec.child.lineage_sha256,
        }
    )


def _scan_value(
    value: Any,
    *,
    component_id: str,
    path: str,
    forbidden_values: frozenset[str],
) -> list[PublicIdentityLeakageFinding]:
    findings: list[PublicIdentityLeakageFinding] = []
    if isinstance(value, Mapping):
        for raw_key, item in value.items():
            key = str(raw_key)
            item_path = f"{path}.{key}"
            if key.lower() in _FORBIDDEN_IDENTITY_KEYS:
                findings.append(
                    PublicIdentityLeakageFinding(
                        component_id=component_id,
                        path=item_path,
                        finding_kind="forbidden_identity_key",
                        matched_value=key,
                    )
                )
            findings.extend(
                _scan_value(
                    item,
                    component_id=component_id,
                    path=item_path,
                    forbidden_values=forbidden_values,
                )
            )
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, item in enumerate(value):
            findings.extend(
                _scan_value(
                    item,
                    component_id=component_id,
                    path=f"{path}[{index}]",
                    forbidden_values=forbidden_values,
                )
            )
    elif isinstance(value, str) and value in forbidden_values:
        findings.append(
            PublicIdentityLeakageFinding(
                component_id=component_id,
                path=path,
                finding_kind="forbidden_identity_value",
                matched_value=value,
            )
        )
    return findings


def audit_public_identity_leakage(
    bundle: PublicContractBundle,
    *,
    spec: WorldForkSpec,
) -> tuple[PublicIdentityLeakageFinding, ...]:
    """Find audit-only fork identity in agent-facing contract payloads."""

    forbidden_values = _forbidden_exact_values(spec)
    findings = [
        finding
        for component_id, payload in bundle.component_payloads.items()
        for finding in _scan_value(
            payload,
            component_id=component_id,
            path="$",
            forbidden_values=forbidden_values,
        )
    ]
    return tuple(
        sorted(
            findings,
            key=lambda finding: (
                finding.component_id,
                finding.path,
                finding.finding_kind,
                finding.matched_value,
            ),
        )
    )


def certify_public_contract_invariance(
    *,
    spec: WorldForkSpec,
    inventory: WorldComponentInventory,
    parent_bundle: PublicContractBundle,
    child_bundle: PublicContractBundle,
) -> PublicContractInvarianceCertificate:
    """Compare every public payload and bind it to the fork specification."""

    spec.validate(inventory)
    public_ids = _public_component_ids(inventory)
    if tuple(parent_bundle.component_payloads) != public_ids:
        raise PublicContractCertificateError("parent bundle is not canonically ordered")
    if tuple(child_bundle.component_payloads) != public_ids:
        raise PublicContractCertificateError("child bundle is not canonically ordered")
    parent_hashes = parent_bundle.component_sha256
    child_hashes = child_bundle.component_sha256
    results = tuple(
        PublicContractComponentResult(
            component_id=component_id,
            parent_payload_sha256=parent_hashes[component_id],
            child_payload_sha256=child_hashes[component_id],
            payloads_equal=(
                parent_bundle.component_payloads[component_id]
                == child_bundle.component_payloads[component_id]
            ),
            parent_spec_bound=(
                parent_hashes[component_id] == spec.parent.component_sha256[component_id]
            ),
            child_spec_bound=(
                child_hashes[component_id] == spec.child.component_sha256[component_id]
            ),
        )
        for component_id in public_ids
    )
    leakage = (
        *audit_public_identity_leakage(parent_bundle, spec=spec),
        *audit_public_identity_leakage(child_bundle, spec=spec),
    )
    return PublicContractInvarianceCertificate(
        fork_id=spec.fork_id,
        fork_spec_sha256=spec.content_sha256,
        inventory_id=inventory.inventory_id,
        inventory_sha256=inventory.content_sha256,
        parent_bundle_sha256=parent_bundle.content_sha256,
        child_bundle_sha256=child_bundle.content_sha256,
        component_results=results,
        leakage_findings=tuple(leakage),
    )


__all__ = [
    "PUBLIC_CONTRACT_BUNDLE_SCHEMA_VERSION",
    "PUBLIC_CONTRACT_CERTIFICATE_VERSION",
    "PublicContractBundle",
    "PublicContractCertificateError",
    "PublicContractComponentResult",
    "PublicContractInvarianceCertificate",
    "PublicIdentityLeakageFinding",
    "audit_public_identity_leakage",
    "build_public_contract_bundle",
    "certify_public_contract_invariance",
]
