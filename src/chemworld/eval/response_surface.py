"""Deterministic response-surface audit for serious benchmark tasks."""

from __future__ import annotations

from typing import Any

import gymnasium as gym
import numpy as np

import chemworld  # noqa: F401
from chemworld.agents.task_recipes import sample_task_recipe
from chemworld.tasks import SERIOUS_TASK_IDS, get_task
from chemworld.world.recipes import compile_recipe

RESPONSE_SURFACE_AUDIT_VERSION = "chemworld-response-surface-audit-0.2"
PRIMARY_OBSERVATION_FIELDS = {
    "partition-discovery": "product_in_organic",
    "reaction-to-crystallization": "crystal_yield",
    "reaction-to-distillation": "distillate_purity",
    "flow-reaction-optimization": "flow_conversion",
    "electrochemical-conversion": "selective_product_yield",
    "equilibrium-characterization": "equilibrium_confidence",
}


def audit_serious_response_surfaces(
    *,
    samples_per_seed: int = 12,
    task_ids: tuple[str, ...] = SERIOUS_TASK_IDS,
) -> dict[str, Any]:
    if samples_per_seed < 2:
        raise ValueError("samples_per_seed must be at least two")
    task_reports: dict[str, dict[str, Any]] = {}
    for task_index, task_id in enumerate(task_ids):
        task = get_task(task_id)
        scores: list[float] = []
        primary_values: list[float] = []
        invalid_steps = 0
        final_assays = 0
        seed_reports: dict[str, dict[str, Any]] = {}
        for seed in task.seeds:
            seed_scores: list[float] = []
            seed_primary_values: list[float] = []
            rng = np.random.default_rng(91_003 + 10_007 * task_index + seed)
            for _ in range(samples_per_seed):
                env = gym.make(
                    task.env_id,
                    task_id=task.task_id,
                    world_split=task.world_split,
                    budget=task.budget,
                    objective=task.objective,
                    seed=seed,
                )
                try:
                    _, task_info = env.reset(seed=seed)
                    recipe = sample_task_recipe(task_info, rng)
                    final_observation: dict[str, Any] = {}
                    final_info: dict[str, Any] = {}
                    for action in compile_recipe(recipe, task_info=task_info):
                        observation, _, _, _, info = env.step(action)
                        final_observation = observation
                        final_info = info
                        invalid_steps += int(
                            bool(info["constraint_flags"].get("precondition_failed", False))
                        )
                    score = final_info.get("leaderboard_score")
                    if score is None:
                        raise RuntimeError(f"{task_id} recipe did not produce a final assay")
                    final_assays += 1
                    scores.append(float(score))
                    seed_scores.append(float(score))
                    primary_field = PRIMARY_OBSERVATION_FIELDS[task_id]
                    primary_value = final_observation.get(primary_field)
                    if primary_value is not None:
                        scalar_primary = float(np.asarray(primary_value).reshape(-1)[0])
                        primary_values.append(scalar_primary)
                        seed_primary_values.append(scalar_primary)
                finally:
                    env.close()
            seed_score_array = np.asarray(seed_scores, dtype=float)
            seed_primary_array = np.asarray(seed_primary_values, dtype=float)
            seed_reports[str(seed)] = {
                "score": _distribution_summary(seed_score_array),
                "primary_metric_distribution": _distribution_summary(seed_primary_array),
                "sampled_recipe_ceiling_score": float(np.max(seed_score_array)),
            }
        score_array = np.asarray(scores, dtype=float)
        primary_array = np.asarray(primary_values, dtype=float)
        task_reports[task_id] = {
            "task_contract_hash": task.contract_hash,
            "seeds": list(task.seeds),
            "samples_per_seed": samples_per_seed,
            "sample_count": len(scores),
            "invalid_step_count": invalid_steps,
            "final_assay_count": final_assays,
            "score": _distribution_summary(score_array),
            "primary_metric": PRIMARY_OBSERVATION_FIELDS[task_id],
            "primary_metric_distribution": _distribution_summary(primary_array),
            "sampled_recipe_ceiling_score": float(np.max(score_array)),
            "seed_reports": seed_reports,
        }
    return {
        "schema_version": RESPONSE_SURFACE_AUDIT_VERSION,
        "task_ids": list(task_ids),
        "samples_per_seed": samples_per_seed,
        "reference_semantics": {
            "kind": "deterministic_random_recipe_probe",
            "is_oracle": False,
            "may_be_exceeded_by_future_methods": True,
            "regret_reference_allowed": False,
        },
        "passed": all(
            report["invalid_step_count"] == 0
            and report["score"]["spread"] >= 0.01
            and report["final_assay_count"] == report["sample_count"]
            for report in task_reports.values()
        ),
        "tasks": task_reports,
    }


def _distribution_summary(values: np.ndarray) -> dict[str, float | int]:
    if values.size == 0:
        return {
            "count": 0,
            "minimum": 0.0,
            "q25": 0.0,
            "median": 0.0,
            "q75": 0.0,
            "maximum": 0.0,
            "mean": 0.0,
            "std": 0.0,
            "spread": 0.0,
        }
    return {
        "count": int(values.size),
        "minimum": float(np.min(values)),
        "q25": float(np.quantile(values, 0.25)),
        "median": float(np.median(values)),
        "q75": float(np.quantile(values, 0.75)),
        "maximum": float(np.max(values)),
        "mean": float(np.mean(values)),
        "std": float(np.std(values)),
        "spread": float(np.max(values) - np.min(values)),
    }


__all__ = [
    "RESPONSE_SURFACE_AUDIT_VERSION",
    "audit_serious_response_surfaces",
]
