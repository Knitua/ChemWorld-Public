"""Fixed, auditable task maturity and runtime-dependency reports."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from chemworld.physchem.maturity import ModelExecutionRole
from chemworld.runtime.model_reachability import (
    MODEL_REACHABILITY_SCHEMA_VERSION,
    ModelReachabilityRegistry,
    default_model_reachability_registry,
)
from chemworld.runtime.profiles import TaskRuntimeProfile
from chemworld.tasks import TaskSpec, get_task, list_tasks

MATURITY_AUDIT_SCHEMA_VERSION = "chemworld-maturity-audit-0.1"
DEFAULT_MATURITY_AUDIT_PATH = Path("runs/audits/maturity-audit.json")
_CORE_EVIDENCE_PATHS = (
    "src/chemworld/tasks.py",
    "src/chemworld/runtime/profiles.py",
    "src/chemworld/runtime/domain_service_registry.py",
    "src/chemworld/runtime/kernel_registry.py",
    "src/chemworld/runtime/model_reachability.py",
)


def build_maturity_audit(
    task_ids: tuple[str, ...] | None = None,
    *,
    repository_root: Path | None = None,
) -> dict[str, Any]:
    """Build a deterministic report for every registered task.

    The report deliberately preserves declaration gaps. A gap is evidence for
    WF-00 remediation, not a reason to silently rewrite a task contract.
    """

    root = Path.cwd() if repository_root is None else repository_root
    registry = default_model_reachability_registry()
    tasks = tuple(list_tasks()) if task_ids is None else tuple(get_task(item) for item in task_ids)
    task_reports = tuple(
        _task_report(task, registry, root) for task in sorted(tasks, key=lambda item: item.task_id)
    )
    structural_findings = [finding.to_dict() for finding in registry.structural_findings()]
    declaration_gap_count = sum(
        len(report["declared_but_unreachable"]) + len(report["reachable_but_undeclared"])
        for report in task_reports
    )
    report: dict[str, Any] = {
        "schema_version": MATURITY_AUDIT_SCHEMA_VERSION,
        "source_reachability_schema_version": MODEL_REACHABILITY_SCHEMA_VERSION,
        "world_law_id": task_reports[0]["world_law_id"] if task_reports else None,
        "task_count": len(task_reports),
        "provider_count": len(registry.providers.providers),
        "route_count": len(registry.routes),
        "contract_integrity_passed": not any(
            finding["severity"] == "error" for finding in structural_findings
        ),
        "role_boundary_passed": not any(
            finding["check_id"] == "reference_runtime_separation" for finding in structural_findings
        ),
        "provider_role_catalog": {
            provider.model_id: provider.role.value
            for provider in sorted(registry.providers.providers, key=lambda item: item.model_id)
        },
        "declaration_alignment_status": (
            "aligned" if declaration_gap_count == 0 else "gaps_detected"
        ),
        "declaration_gap_count": declaration_gap_count,
        "structural_findings": structural_findings,
        "evidence_paths": sorted(
            {path for task_report in task_reports for path in task_report["evidence_paths"]}
        ),
        "tasks": list(task_reports),
        "report_hash": None,
    }
    report["report_hash"] = _report_hash(report)
    return report


def validate_maturity_audit_report(
    report: dict[str, Any],
    *,
    repository_root: Path | None = None,
    require_all_tasks: bool = True,
) -> list[str]:
    """Return explicit schema, hash, evidence, and coverage findings."""

    root = Path.cwd() if repository_root is None else repository_root
    errors: list[str] = []
    if report.get("schema_version") != MATURITY_AUDIT_SCHEMA_VERSION:
        errors.append("unsupported maturity audit schema")
    tasks = report.get("tasks")
    if not isinstance(tasks, list):
        return ["tasks must be a list"]
    task_ids: list[str] = []
    for item in tasks:
        if isinstance(item, dict) and isinstance(item.get("task_id"), str):
            task_ids.append(item["task_id"])
    if len(task_ids) != len(tasks) or len(task_ids) != len(set(task_ids)):
        errors.append("tasks must contain unique task_id entries")
    expected_ids = {task.task_id for task in list_tasks()}
    if require_all_tasks and set(task_ids) != expected_ids:
        missing = sorted(expected_ids - set(task_ids))
        extra = sorted(set(task_ids) - expected_ids)
        errors.append(f"task coverage mismatch: missing={missing}, extra={extra}")
    if report.get("task_count") != len(tasks):
        errors.append("task_count does not match tasks")
    registry = default_model_reachability_registry()
    for item in tasks:
        if not isinstance(item, dict):
            errors.append("task report entries must be objects")
            continue
        task_id = item.get("task_id")
        if not isinstance(task_id, str):
            errors.append("task report task_id must be a string")
            continue
        try:
            task = get_task(task_id)
        except KeyError:
            errors.append(f"unknown task in report: {task_id}")
            continue
        profile = TaskRuntimeProfile.from_task(task)
        if item.get("task_contract_hash") != task.contract_hash:
            errors.append(f"task contract hash mismatch: {task_id}")
        if item.get("runtime_profile_hash") != profile.profile_hash:
            errors.append(f"runtime profile hash mismatch: {task_id}")
        if item.get("actual_model_ids") != sorted(item.get("actual_model_ids", ())):
            errors.append(f"actual model ids are not sorted: {task_id}")
        for path in item.get("evidence_paths", ()):
            if not isinstance(path, str) or not (root / path).is_file():
                errors.append(f"missing evidence path for {task_id}: {path}")
        actual_model_ids = set(item.get("actual_model_ids", ()))
        try:
            expected_model_ids = set(registry.reachable_model_ids(profile))
        except (KeyError, ValueError) as error:
            errors.append(f"cannot resolve runtime dependencies for {task_id}: {error}")
            continue
        if actual_model_ids != expected_model_ids:
            errors.append(f"actual model dependency mismatch: {task_id}")
        expected_minimum = _minimum_maturity(registry, expected_model_ids)
        if item.get("minimum_actual_maturity") != expected_minimum:
            errors.append(f"minimum actual maturity mismatch: {task_id}")
        expected_roles = {
            model_id: registry.providers.get(model_id).role.value for model_id in expected_model_ids
        }
        if item.get("actual_provider_roles") != expected_roles:
            errors.append(f"actual provider role mismatch: {task_id}")
        actual_partition = item.get("actual_role_partition")
        if not isinstance(actual_partition, dict):
            errors.append(f"missing actual role partition: {task_id}")
        else:
            for role in ModelExecutionRole:
                expected_role_ids = sorted(
                    model_id for model_id, value in expected_roles.items() if value == role.value
                )
                if actual_partition.get(role.value) != expected_role_ids:
                    errors.append(f"actual role partition mismatch: {task_id}:{role.value}")
        declared_roles = item.get("declared_provider_roles")
        if not isinstance(declared_roles, dict):
            errors.append(f"missing declared provider roles: {task_id}")
        else:
            for model_id in item.get("declared_model_ids", ()):
                provider_role = (
                    registry.providers.get(model_id).role.value
                    if model_id in {provider.model_id for provider in registry.providers.providers}
                    else "unregistered"
                )
                if declared_roles.get(model_id) != provider_role:
                    errors.append(f"declared provider role mismatch: {task_id}:{model_id}")
    if report.get("report_hash") != _report_hash({**report, "report_hash": None}):
        errors.append("report_hash mismatch")
    for path in report.get("evidence_paths", ()):
        if not isinstance(path, str) or not (root / path).is_file():
            errors.append(f"missing global evidence path: {path}")
    return errors


def write_maturity_audit_report(
    output: Path = DEFAULT_MATURITY_AUDIT_PATH,
    *,
    repository_root: Path | None = None,
) -> dict[str, Any]:
    """Write and validate the fixed full-task JSON report."""

    root = Path.cwd() if repository_root is None else repository_root
    report = build_maturity_audit(repository_root=root)
    errors = validate_maturity_audit_report(report, repository_root=root)
    if errors:
        raise ValueError("invalid maturity audit report: " + "; ".join(errors))
    destination = output if output.is_absolute() else root / output
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report


def _task_report(
    task: TaskSpec,
    registry: ModelReachabilityRegistry,
    repository_root: Path,
) -> dict[str, Any]:
    profile = TaskRuntimeProfile.from_task(task)
    actual_model_ids = sorted(registry.reachable_model_ids(profile))
    routes = [
        registry.route_for_operation(operation).to_dict()
        for operation in sorted(profile.allowed_operations)
    ]
    declared_model_ids = sorted(
        model_id for module in task.kernel_maturity.modules for model_id in module.model_ids
    )
    registered_model_ids = {provider.model_id for provider in registry.providers.providers}
    provider_maturity = {
        model_id: registry.providers.get(model_id).maturity.value for model_id in actual_model_ids
    }
    actual_provider_roles = {
        model_id: registry.providers.get(model_id).role.value for model_id in actual_model_ids
    }
    declared_provider_roles = {
        model_id: (
            registry.providers.get(model_id).role.value
            if model_id in registered_model_ids
            else "unregistered"
        )
        for model_id in declared_model_ids
    }
    actual_role_partition = {
        role.value: sorted(
            model_id
            for model_id, provider_role in actual_provider_roles.items()
            if provider_role == role.value
        )
        for role in ModelExecutionRole
    }
    evidence_paths = set(_CORE_EVIDENCE_PATHS)
    for model_id in actual_model_ids:
        provider = registry.providers.get(model_id)
        module_name = provider.provider_path.rsplit(".", 1)[0]
        source_path = "src/" + module_name.replace(".", "/") + ".py"
        if (repository_root / source_path).is_file():
            evidence_paths.add(source_path)
    return {
        "task_id": task.task_id,
        "world_law_id": task.world_law_id,
        "task_contract_hash": task.contract_hash,
        "runtime_profile_hash": profile.profile_hash,
        "declared_module_maturity": task.kernel_maturity.to_dict(),
        "declared_model_ids": declared_model_ids,
        "actual_dependencies": {
            "operations": sorted(profile.allowed_operations),
            "domain_services": sorted(profile.required_domain_services),
            "kernels": sorted(profile.required_kernels),
            "models": actual_model_ids,
        },
        "actual_model_ids": actual_model_ids,
        "provider_maturity": provider_maturity,
        "actual_provider_roles": actual_provider_roles,
        "declared_provider_roles": declared_provider_roles,
        "actual_role_partition": actual_role_partition,
        "minimum_declared_maturity": task.kernel_maturity.lowest_level.value,
        "minimum_actual_maturity": _minimum_maturity(registry, set(actual_model_ids)),
        "declared_but_unreachable": sorted(set(declared_model_ids) - set(actual_model_ids)),
        "reachable_but_undeclared": sorted(set(actual_model_ids) - set(declared_model_ids)),
        "alignment_status": (
            "aligned" if set(declared_model_ids) == set(actual_model_ids) else "gaps_detected"
        ),
        "routes": routes,
        "evidence_paths": sorted(evidence_paths),
    }


def _minimum_maturity(
    registry: ModelReachabilityRegistry,
    model_ids: set[str],
) -> str:
    if not model_ids:
        return "not_applicable"
    return min(
        (registry.providers.get(model_id).maturity for model_id in model_ids),
        key=lambda level: level.rank,
    ).value


def _report_hash(report: dict[str, Any]) -> str:
    payload = {key: value for key, value in report.items() if key != "report_hash"}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


__all__ = [
    "DEFAULT_MATURITY_AUDIT_PATH",
    "MATURITY_AUDIT_SCHEMA_VERSION",
    "build_maturity_audit",
    "validate_maturity_audit_report",
    "write_maturity_audit_report",
]
