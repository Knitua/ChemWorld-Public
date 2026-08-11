"""Empirical validity checks for serious-task baseline reports."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from chemworld.eval.baseline_report import SERIOUS_BASELINE_AGENTS
from chemworld.task_design import SERIOUS_TASK_DESIGNS
from chemworld.tasks import SERIOUS_TASK_IDS, get_task

BENCHMARK_VALIDATION_SCHEMA_VERSION = "chemworld-benchmark-validation-0.1"
PRIMARY_METRIC_FIELDS = {
    task_id: f"mean_{design.primary_metric}"
    for task_id, design in SERIOUS_TASK_DESIGNS.items()
}


@dataclass(frozen=True)
class EmpiricalCheck:
    check_id: str
    passed: bool
    message: str
    value: Any = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "check_id": self.check_id,
            "passed": self.passed,
            "message": self.message,
            "value": self.value,
        }


def validate_serious_baseline_report(report: dict[str, Any]) -> dict[str, Any]:
    """Evaluate whether a baseline report provides benchmark-freezing evidence."""

    rows = report.get("summary_rows")
    if not isinstance(rows, list):
        raise ValueError("baseline report must contain summary_rows")
    by_task: dict[str, dict[str, dict[str, Any]]] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("baseline summary rows must be objects")
        task_id = str(row.get("task_id", ""))
        agent_name = str(row.get("agent_name", ""))
        by_task.setdefault(task_id, {})[agent_name] = row

    task_evidence: dict[str, dict[str, Any]] = {}
    for task_id in SERIOUS_TASK_IDS:
        task = get_task(task_id)
        agent_rows = by_task.get(task_id, {})
        required_agents = tuple(SERIOUS_BASELINE_AGENTS)
        missing_agents = sorted(set(required_agents) - set(agent_rows))
        official_rows = [agent_rows[name] for name in required_agents if name in agent_rows]
        score_values = [float(row.get("mean_total_score", 0.0)) for row in official_rows]
        primary_field = PRIMARY_METRIC_FIELDS[task_id]
        primary_values = [float(row.get(primary_field, 0.0)) for row in official_rows]
        observed_seed_sets = {
            tuple(int(seed) for seed in row.get("seeds", ())) for row in official_rows
        }
        invalid_rates = [
            float(row.get("mean_invalid_action_rate", 1.0)) for row in official_rows
        ]
        assay_counts = [
            float(row.get("mean_final_assay_count", 0.0)) for row in official_rows
        ]
        success_rates = [float(row.get("success_rate", 0.0)) for row in official_rows]
        bo_rows = [
            agent_rows[name]
            for name in ("gp_bo", "safe_gp_bo")
            if name in agent_rows
        ]
        bo_entered = [float(row.get("mean_bo_entered_acquisition", 0.0)) for row in bo_rows]
        bo_acquisitions = [
            float(row.get("mean_bo_acquisition_recipe_count", 0.0)) for row in bo_rows
        ]
        distinct_scores = len({round(value, 5) for value in score_values})
        score_spread = max(score_values) - min(score_values) if score_values else 0.0
        primary_spread = (
            max(primary_values) - min(primary_values) if primary_values else 0.0
        )
        checks = (
            EmpiricalCheck(
                "required_agents",
                not missing_agents,
                "all official task-valid baselines must be present",
                missing_agents,
            ),
            EmpiricalCheck(
                "seed_coverage",
                bool(official_rows)
                and observed_seed_sets == {tuple(task.seeds)}
                and all(int(row.get("runs", 0)) == len(task.seeds) for row in official_rows),
                "every official baseline must cover the frozen task seed suite",
                sorted(observed_seed_sets),
            ),
            EmpiricalCheck(
                "valid_actions",
                bool(invalid_rates) and max(invalid_rates) <= 1.0e-12,
                "official task-aware baselines must not rely on invalid actions",
                max(invalid_rates) if invalid_rates else None,
            ),
            EmpiricalCheck(
                "repeated_experiments",
                bool(assay_counts) and min(assay_counts) >= 2.0,
                "serious campaign baselines must complete more than one experiment",
                min(assay_counts) if assay_counts else None,
            ),
            EmpiricalCheck(
                "active_learning_phase",
                len(bo_rows) == 2
                and min(bo_entered, default=0.0) >= 0.8
                and min(bo_acquisitions, default=0.0) >= 1.0,
                "GP baselines must apply their learned surrogate in later experiments",
                {
                    "entered": bo_entered,
                    "mean_acquisition_recipes": bo_acquisitions,
                },
            ),
            EmpiricalCheck(
                "score_range",
                bool(score_values)
                and max(score_values) >= 0.02
                and max(score_values) <= 0.98,
                "scores must avoid universal floor and ceiling saturation",
                {
                    "minimum": min(score_values, default=0.0),
                    "maximum": max(score_values, default=0.0),
                },
            ),
            EmpiricalCheck(
                "strategy_separation",
                score_spread >= 0.01 and distinct_scores >= 3,
                "official baselines must produce at least three distinguishable outcomes",
                {"spread": score_spread, "distinct_scores": distinct_scores},
            ),
            EmpiricalCheck(
                "success_threshold_calibration",
                bool(success_rates)
                and max(success_rates) >= 0.2
                and min(success_rates) <= 0.8,
                "the frozen success threshold must be reachable without saturation",
                {
                    "minimum_success_rate": min(success_rates, default=0.0),
                    "maximum_success_rate": max(success_rates, default=0.0),
                },
            ),
            EmpiricalCheck(
                "primary_metric_sensitivity",
                bool(official_rows)
                and primary_field in official_rows[0]
                and primary_spread >= 1.0e-4,
                "the primary metric must be reported and respond to strategy changes",
                {"field": primary_field, "spread": primary_spread},
            ),
        )
        validated = all(check.passed for check in checks)
        task_evidence[task_id] = {
            "validated": validated,
            "task_contract_hash": task.contract_hash,
            "primary_metric_field": primary_field,
            "score_spread": score_spread,
            "primary_metric_spread": primary_spread,
            "checks": [check.to_dict() for check in checks],
        }

    validated_count = sum(
        bool(evidence["validated"]) for evidence in task_evidence.values()
    )
    return {
        "schema_version": BENCHMARK_VALIDATION_SCHEMA_VERSION,
        "suite_id": "chemworld-serious-candidate",
        "validated": validated_count == len(SERIOUS_TASK_IDS),
        "validated_task_count": validated_count,
        "task_count": len(SERIOUS_TASK_IDS),
        "task_ids": list(SERIOUS_TASK_IDS),
        "baseline_report_schema_version": report.get("schema_version"),
        "baseline_report_sha256": _canonical_sha256(report),
        "baseline_agents": list(SERIOUS_BASELINE_AGENTS),
        "task_evidence": task_evidence,
    }


def load_official_validation(path: str | Path | None = None) -> dict[str, Any] | None:
    if path is None:
        return None
    source = Path(path)
    if not source.is_file():
        return None
    payload = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("official benchmark validation must be a JSON object")
    if payload.get("schema_version") != BENCHMARK_VALIDATION_SCHEMA_VERSION:
        raise ValueError("unsupported official benchmark validation schema")
    task_ids = payload.get("task_ids")
    if task_ids != list(SERIOUS_TASK_IDS):
        raise ValueError("official benchmark validation has unexpected task coverage")
    if payload.get("baseline_agents") != list(SERIOUS_BASELINE_AGENTS):
        raise ValueError("official benchmark validation has unexpected baseline coverage")
    evidence_by_task = payload.get("task_evidence")
    if not isinstance(evidence_by_task, dict):
        raise ValueError("official benchmark validation must contain task_evidence")
    if set(evidence_by_task) != set(SERIOUS_TASK_IDS):
        raise ValueError("official benchmark validation evidence is incomplete")
    validated_count = sum(
        isinstance(evidence, dict) and evidence.get("validated") is True
        for evidence in evidence_by_task.values()
    )
    if payload.get("validated_task_count") != validated_count:
        raise ValueError("official benchmark validation count is inconsistent")
    if payload.get("task_count") != len(SERIOUS_TASK_IDS):
        raise ValueError("official benchmark validation task count is inconsistent")
    suite_validated = validated_count == len(SERIOUS_TASK_IDS)
    if payload.get("validated") is not suite_validated:
        raise ValueError("official benchmark validation suite status is inconsistent")
    return payload


def official_empirical_statuses(
    path: str | Path | None = None,
) -> dict[str, str]:
    payload = load_official_validation(path)
    statuses = dict.fromkeys(SERIOUS_TASK_IDS, "candidate")
    if payload is None or payload.get("validated") is not True:
        return statuses
    evidence_by_task = payload.get("task_evidence", {})
    if not isinstance(evidence_by_task, dict):
        return statuses
    for task_id in SERIOUS_TASK_IDS:
        evidence = evidence_by_task.get(task_id)
        if not isinstance(evidence, dict):
            continue
        current_hash = get_task(task_id).contract_hash
        if evidence.get("validated") is True and evidence.get("task_contract_hash") == current_hash:
            statuses[task_id] = "validated"
    return statuses


def write_validation_artifact(
    report: dict[str, Any],
    output_path: str | Path,
) -> dict[str, Any]:
    artifact = validate_serious_baseline_report(report)
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(artifact, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return artifact


def _canonical_sha256(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


__all__ = [
    "BENCHMARK_VALIDATION_SCHEMA_VERSION",
    "PRIMARY_METRIC_FIELDS",
    "EmpiricalCheck",
    "load_official_validation",
    "official_empirical_statuses",
    "validate_serious_baseline_report",
    "write_validation_artifact",
]
