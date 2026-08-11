"""Dataset-level provenance and deterministic component-data conflict audits."""

from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
from typing import Any

from chemworld.physchem.specs import (
    ComponentConflictPolicy,
    ComponentConflictResolution,
    ComponentFieldCandidate,
    resolve_component_field_conflict,
)

DATA_PROVENANCE_CARD_SCHEMA_VERSION = "chemworld-data-provenance-card-0.1"


def _digest(payload: dict[str, object]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


@dataclass(frozen=True)
class DataSourceProvenance:
    source_id: str
    priority: int
    citation: str
    version: str = ""
    license: str = ""
    checksum: str = ""

    def __post_init__(self) -> None:
        if not self.source_id or not self.citation:
            raise ValueError("source_id and citation cannot be empty")
        if self.priority < 0:
            raise ValueError("source priority must be nonnegative")

    def to_dict(self) -> dict[str, object]:
        return {
            "source_id": self.source_id,
            "priority": self.priority,
            "citation": self.citation,
            "version": self.version,
            "license": self.license,
            "checksum": self.checksum,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> DataSourceProvenance:
        return cls(
            source_id=str(payload["source_id"]),
            priority=int(str(payload["priority"])),
            citation=str(payload["citation"]),
            version=str(payload.get("version", "")),
            license=str(payload.get("license", "")),
            checksum=str(payload.get("checksum", "")),
        )


@dataclass(frozen=True)
class DataConflictFinding:
    field_id: str
    severity: str
    message: str

    def __post_init__(self) -> None:
        if self.severity not in {"warning", "error"}:
            raise ValueError("finding severity must be warning or error")
        if not self.field_id or not self.message:
            raise ValueError("finding field_id and message cannot be empty")

    def to_dict(self) -> dict[str, str]:
        return {
            "field_id": self.field_id,
            "severity": self.severity,
            "message": self.message,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> DataConflictFinding:
        return cls(
            field_id=str(payload["field_id"]),
            severity=str(payload["severity"]),
            message=str(payload["message"]),
        )


@dataclass(frozen=True)
class ComponentDataConflictReport:
    policy: ComponentConflictPolicy
    sources: tuple[DataSourceProvenance, ...]
    resolutions: tuple[ComponentConflictResolution, ...]
    findings: tuple[DataConflictFinding, ...]

    def __post_init__(self) -> None:
        source_ids = [source.source_id for source in self.sources]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("duplicate data source ids are not allowed")
        resolution_fields = [resolution.field_id for resolution in self.resolutions]
        if len(resolution_fields) != len(set(resolution_fields)):
            raise ValueError("duplicate field resolutions are not allowed")

    @property
    def accepted(self) -> bool:
        return not any(finding.severity == "error" for finding in self.findings)

    @property
    def warning_count(self) -> int:
        return sum(finding.severity == "warning" for finding in self.findings)

    @property
    def error_count(self) -> int:
        return sum(finding.severity == "error" for finding in self.findings)

    @property
    def digest(self) -> str:
        return _digest(self.to_dict(include_digest=False))

    def to_dict(self, *, include_digest: bool = True) -> dict[str, object]:
        payload: dict[str, object] = {
            "accepted": self.accepted,
            "warning_count": self.warning_count,
            "error_count": self.error_count,
            "policy": self.policy.to_dict(),
            "sources": [source.to_dict() for source in self.sources],
            "resolutions": [resolution.to_dict() for resolution in self.resolutions],
            "findings": [finding.to_dict() for finding in self.findings],
        }
        if include_digest:
            payload["digest"] = self.digest
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> ComponentDataConflictReport:
        report = cls(
            policy=ComponentConflictPolicy.from_dict(dict(payload["policy"])),
            sources=tuple(
                DataSourceProvenance.from_dict(dict(item)) for item in payload.get("sources", ())
            ),
            resolutions=tuple(
                ComponentConflictResolution.from_dict(dict(item))
                for item in payload.get("resolutions", ())
            ),
            findings=tuple(
                DataConflictFinding.from_dict(dict(item)) for item in payload.get("findings", ())
            ),
        )
        expected_digest = payload.get("digest")
        if expected_digest is not None and str(expected_digest) != report.digest:
            raise ValueError("component data conflict report digest mismatch")
        return report


@dataclass(frozen=True)
class DatasetProvenanceCard:
    dataset_id: str
    registry_digest: str
    report: ComponentDataConflictReport

    def __post_init__(self) -> None:
        if not self.dataset_id or not self.registry_digest:
            raise ValueError("dataset_id and registry_digest cannot be empty")

    @property
    def digest(self) -> str:
        return _digest(self.to_dict(include_digest=False))

    def to_dict(self, *, include_digest: bool = True) -> dict[str, object]:
        payload: dict[str, object] = {
            "schema_version": DATA_PROVENANCE_CARD_SCHEMA_VERSION,
            "dataset_id": self.dataset_id,
            "registry_digest": self.registry_digest,
            "accepted": self.report.accepted,
            "conflict_report": self.report.to_dict(),
        }
        if include_digest:
            payload["digest"] = self.digest
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> DatasetProvenanceCard:
        schema_version = str(payload.get("schema_version", ""))
        if schema_version != DATA_PROVENANCE_CARD_SCHEMA_VERSION:
            raise ValueError(f"unsupported data provenance schema {schema_version!r}")
        card = cls(
            dataset_id=str(payload["dataset_id"]),
            registry_digest=str(payload["registry_digest"]),
            report=ComponentDataConflictReport.from_dict(dict(payload["conflict_report"])),
        )
        expected_digest = payload.get("digest")
        if expected_digest is not None and str(expected_digest) != card.digest:
            raise ValueError("dataset provenance card digest mismatch")
        return card


def audit_component_data_conflicts(
    candidates: tuple[ComponentFieldCandidate, ...],
    policy: ComponentConflictPolicy,
    *,
    sources: tuple[DataSourceProvenance, ...],
) -> ComponentDataConflictReport:
    """Resolve all fields and preserve warnings/errors instead of losing context."""

    if not candidates:
        raise ValueError("at least one data candidate is required")
    source_ids = {source.source_id for source in sources}
    if len(source_ids) != len(sources):
        raise ValueError("duplicate data source ids are not allowed")
    grouped: dict[str, list[ComponentFieldCandidate]] = {}
    findings: list[DataConflictFinding] = []
    for candidate in candidates:
        grouped.setdefault(candidate.field_id, []).append(candidate)
        if candidate.source_id not in source_ids:
            findings.append(
                DataConflictFinding(
                    candidate.field_id,
                    "error",
                    f"candidate references undefined source {candidate.source_id!r}",
                )
            )

    resolutions: list[ComponentConflictResolution] = []
    for field_id in sorted(grouped):
        field_candidates = tuple(grouped[field_id])
        if field_id in policy.required_uncertainty_fields:
            missing_sources = sorted(
                candidate.source_id
                for candidate in field_candidates
                if candidate.uncertainty is None
            )
            if missing_sources and policy.missing_uncertainty_mode != "ignore":
                severity = "error" if policy.missing_uncertainty_mode == "raise" else "warning"
                findings.append(
                    DataConflictFinding(
                        field_id,
                        severity,
                        "missing uncertainty metadata for sources: " + ", ".join(missing_sources),
                    )
                )
        try:
            resolution = resolve_component_field_conflict(
                field_id,
                field_candidates,
                policy,
            )
        except ValueError as exc:
            findings.append(DataConflictFinding(field_id, "error", str(exc)))
            warning_policy = ComponentConflictPolicy(
                mode="warn",
                source_priority=policy.source_priority,
                default_rtol=policy.default_rtol,
                default_atol=policy.default_atol,
                field_rtol=policy.field_rtol,
                field_atol=policy.field_atol,
                required_uncertainty_fields=policy.required_uncertainty_fields,
                missing_uncertainty_mode=policy.missing_uncertainty_mode,
            )
            resolution = resolve_component_field_conflict(
                field_id,
                field_candidates,
                warning_policy,
            )
        else:
            if resolution.status in {"conflict_warning", "preferred"}:
                findings.append(DataConflictFinding(field_id, "warning", resolution.message))
        resolutions.append(resolution)

    ordered_sources = tuple(sorted(sources, key=lambda item: (item.priority, item.source_id)))
    ordered_findings = tuple(
        sorted(findings, key=lambda item: (item.field_id, item.severity, item.message))
    )
    return ComponentDataConflictReport(
        policy=policy,
        sources=ordered_sources,
        resolutions=tuple(resolutions),
        findings=ordered_findings,
    )


def build_dataset_provenance_card(
    report: ComponentDataConflictReport,
    *,
    dataset_id: str,
    registry_digest: str,
) -> DatasetProvenanceCard:
    return DatasetProvenanceCard(dataset_id, registry_digest, report)


__all__ = [
    "DATA_PROVENANCE_CARD_SCHEMA_VERSION",
    "ComponentDataConflictReport",
    "DataConflictFinding",
    "DataSourceProvenance",
    "DatasetProvenanceCard",
    "audit_component_data_conflicts",
    "build_dataset_provenance_card",
]
