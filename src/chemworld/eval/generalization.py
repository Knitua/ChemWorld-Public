"""Public out-of-distribution diagnostics for serious tasks."""

from __future__ import annotations

from typing import Any

import numpy as np

from chemworld.eval.baseline_report import SERIOUS_BASELINE_AGENTS
from chemworld.eval.benchmark_validation import PRIMARY_METRIC_FIELDS
from chemworld.tasks import SERIOUS_TASK_IDS, get_task

GENERALIZATION_AUDIT_VERSION = "chemworld-generalization-audit-0.1"


def compare_public_and_ood_reports(
    public_report: dict[str, Any],
    ood_report: dict[str, Any],
    *,
    ood_seeds: tuple[int, ...],
) -> dict[str, Any]:
    """Compare official public baselines with held-out, non-leaderboard seeds."""

    public_rows = _index_rows(public_report)
    ood_rows = _index_rows(ood_report)
    tasks: dict[str, dict[str, Any]] = {}
    for task_id in SERIOUS_TASK_IDS:
        primary_field = PRIMARY_METRIC_FIELDS[task_id]
        agent_rows: list[dict[str, Any]] = []
        public_scores: list[float] = []
        ood_scores: list[float] = []
        invalid_rates: list[float] = []
        assay_counts: list[float] = []
        for agent_name in SERIOUS_BASELINE_AGENTS:
            public = public_rows[(task_id, agent_name)]
            ood = ood_rows[(task_id, agent_name)]
            public_score = float(public["mean_total_score"])
            ood_score = float(ood["mean_total_score"])
            public_primary = float(public[primary_field])
            ood_primary = float(ood[primary_field])
            public_scores.append(public_score)
            ood_scores.append(ood_score)
            invalid_rates.append(float(ood["mean_invalid_action_rate"]))
            assay_counts.append(float(ood["mean_final_assay_count"]))
            agent_rows.append(
                {
                    "agent_name": agent_name,
                    "public_mean_total_score": public_score,
                    "ood_mean_total_score": ood_score,
                    "score_shift": ood_score - public_score,
                    "public_mean_primary_metric": public_primary,
                    "ood_mean_primary_metric": ood_primary,
                    "primary_metric_shift": ood_primary - public_primary,
                }
            )
        ood_spread = max(ood_scores) - min(ood_scores)
        tasks[task_id] = {
            "task_contract_hash": get_task(task_id).contract_hash,
            "primary_metric_field": primary_field,
            "public_seeds": list(get_task(task_id).seeds),
            "ood_seeds": list(ood_seeds),
            "agent_results": agent_rows,
            "score_diagnostics": {
                "ood_strategy_spread": ood_spread,
                "mean_absolute_shift": float(
                    np.mean(np.abs(np.asarray(ood_scores) - np.asarray(public_scores)))
                ),
                "rank_correlation": _rank_correlation(public_scores, ood_scores),
                "pairwise_ranking_agreement": _pairwise_agreement(
                    public_scores, ood_scores
                ),
            },
            "operational_checks": {
                "all_actions_valid": max(invalid_rates) <= 1.0e-12,
                "campaigns_complete_multiple_assays": min(assay_counts) >= 2.0,
                "strategies_remain_distinguishable": ood_spread >= 0.01,
            },
        }
    passed = all(
        all(task["operational_checks"].values()) for task in tasks.values()
    )
    return {
        "schema_version": GENERALIZATION_AUDIT_VERSION,
        "suite_id": "chemworld-serious-candidate",
        "evaluation_role": "public OOD diagnostic; excluded from leaderboard scoring",
        "task_ids": list(SERIOUS_TASK_IDS),
        "baseline_agents": list(SERIOUS_BASELINE_AGENTS),
        "ood_seeds": list(ood_seeds),
        "passed": passed,
        "tasks": tasks,
    }


def _index_rows(report: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    rows = report.get("summary_rows")
    if not isinstance(rows, list):
        raise ValueError("baseline report must contain summary_rows")
    indexed = {
        (str(row["task_id"]), str(row["agent_name"])): row
        for row in rows
        if isinstance(row, dict)
    }
    expected = {
        (task_id, agent_name)
        for task_id in SERIOUS_TASK_IDS
        for agent_name in SERIOUS_BASELINE_AGENTS
    }
    missing = sorted(expected - set(indexed))
    if missing:
        raise ValueError(f"baseline report is missing task/agent rows: {missing}")
    return indexed


def _rank_correlation(left: list[float], right: list[float]) -> float:
    left_rank = _average_ranks(left)
    right_rank = _average_ranks(right)
    if float(np.std(left_rank)) == 0.0 or float(np.std(right_rank)) == 0.0:
        return 0.0
    return float(np.corrcoef(left_rank, right_rank)[0, 1])


def _average_ranks(values: list[float]) -> np.ndarray:
    array = np.asarray(values, dtype=float)
    order = np.argsort(array, kind="mergesort")
    ranks = np.empty(len(array), dtype=float)
    index = 0
    while index < len(array):
        end = index + 1
        while end < len(array) and array[order[end]] == array[order[index]]:
            end += 1
        ranks[order[index:end]] = 0.5 * (index + end - 1)
        index = end
    return ranks


def _pairwise_agreement(left: list[float], right: list[float]) -> float:
    agreements: list[bool] = []
    for first in range(len(left)):
        for second in range(first + 1, len(left)):
            left_delta = left[first] - left[second]
            right_delta = right[first] - right[second]
            if left_delta == 0.0 or right_delta == 0.0:
                continue
            agreements.append((left_delta > 0.0) == (right_delta > 0.0))
    return float(np.mean(agreements)) if agreements else 0.0


__all__ = [
    "GENERALIZATION_AUDIT_VERSION",
    "compare_public_and_ood_reports",
]
