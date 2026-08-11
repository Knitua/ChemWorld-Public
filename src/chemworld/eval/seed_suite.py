"""Official seed-suite contracts for benchmark evaluation."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from chemworld.tasks import CORE_TASK_IDS, SERIOUS_TASK_IDS, get_task

SEED_SUITE_SCHEMA_VERSION = "chemworld-seed-suite-0.1"
CORE_SEED_SUITE_ID = "chemworld-core-0.2"
SERIOUS_SEED_SUITE_ID = "chemworld-serious-candidate"
PRIVATE_EVAL_SALT_ENV = "CHEMWORLD_PRIVATE_EVAL_SALT"


@dataclass(frozen=True)
class SeedSuiteEntry:
    task_id: str
    world_split: str
    evaluation_role: str
    runnable_seeds: tuple[int, ...]
    published_seeds: tuple[int, ...] | str
    hidden_eval_policy: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "world_split": self.world_split,
            "evaluation_role": self.evaluation_role,
            "runnable_seeds": list(self.runnable_seeds),
            "published_seeds": (
                self.published_seeds
                if isinstance(self.published_seeds, str)
                else list(self.published_seeds)
            ),
            "hidden_eval_policy": self.hidden_eval_policy,
        }


def private_eval_salt_policy() -> dict[str, Any]:
    """Return the public policy for maintainer-side private eval salts."""

    return {
        "salt_environment_variable": PRIVATE_EVAL_SALT_ENV,
        "salt_publication_policy": "never publish the raw salt",
        "artifact_publication_policy": (
            "publish signed result artifacts containing only salt hash, task ids, "
            "seed policy, commit hash, and aggregate metrics"
        ),
        "local_placeholder_policy": (
            "without CHEMWORLD_PRIVATE_EVAL_SALT, private-eval uses a public "
            "placeholder parameterization and is not a leaderboard claim"
        ),
        "hidden_seed_policy": (
            "maintainer may use unpublished seed lists for final leaderboard runs; "
            "public repos only expose smoke/local placeholder seeds"
        ),
    }


def _evaluation_role(world_split: str) -> str:
    if world_split == "public-dev":
        return "development"
    if world_split == "public-test":
        return "public-test"
    if world_split == "private-eval":
        return "hidden-eval-placeholder"
    return "custom"


def seed_entry_for_task(task_id: str) -> SeedSuiteEntry:
    task = get_task(task_id)
    private_policy = private_eval_salt_policy()
    if task.world_split == "private-eval":
        published_seeds: tuple[int, ...] | str = "maintainer-controlled"
        hidden_policy = {
            **private_policy,
            "public_placeholder_seeds": list(task.seeds),
        }
    else:
        published_seeds = task.seeds
        hidden_policy = {"private_eval": "not used for this public task"}
    return SeedSuiteEntry(
        task_id=task.task_id,
        world_split=task.world_split,
        evaluation_role=_evaluation_role(task.world_split),
        runnable_seeds=task.seeds,
        published_seeds=published_seeds,
        hidden_eval_policy=hidden_policy,
    )


def official_seed_entries(
    task_ids: Sequence[str] | None = None,
) -> tuple[SeedSuiteEntry, ...]:
    resolved_task_ids = tuple(CORE_TASK_IDS if task_ids is None else task_ids)
    return tuple(seed_entry_for_task(task_id) for task_id in resolved_task_ids)


def official_seed_suite(
    task_ids: Sequence[str] | None = None,
    *,
    suite_id: str = CORE_SEED_SUITE_ID,
) -> dict[str, Any]:
    entries = official_seed_entries(task_ids)
    return {
        "schema_version": SEED_SUITE_SCHEMA_VERSION,
        "suite_id": suite_id,
        "task_ids": [entry.task_id for entry in entries],
        "task_seed_plan": {
            entry.task_id: list(entry.runnable_seeds) for entry in entries
        },
        "published_seed_plan": {
            entry.task_id: (
                entry.published_seeds
                if isinstance(entry.published_seeds, str)
                else list(entry.published_seeds)
            )
            for entry in entries
        },
        "entries": [entry.to_dict() for entry in entries],
        "private_eval_salt_policy": private_eval_salt_policy(),
    }


def serious_seed_suite() -> dict[str, Any]:
    """Return the public seed plan for the serious-task candidate suite."""

    return official_seed_suite(SERIOUS_TASK_IDS, suite_id=SERIOUS_SEED_SUITE_ID)


def official_seeds_for_task(task_id: str) -> list[int]:
    return list(seed_entry_for_task(task_id).runnable_seeds)


def task_seed_plan(
    task_ids: Sequence[str],
    *,
    override_seeds: Sequence[int] | None = None,
) -> dict[str, list[int]]:
    if override_seeds is not None:
        resolved = [int(seed) for seed in override_seeds]
        return {task_id: list(resolved) for task_id in task_ids}
    return {task_id: official_seeds_for_task(task_id) for task_id in task_ids}


__all__ = [
    "CORE_SEED_SUITE_ID",
    "PRIVATE_EVAL_SALT_ENV",
    "SEED_SUITE_SCHEMA_VERSION",
    "SERIOUS_SEED_SUITE_ID",
    "SeedSuiteEntry",
    "official_seed_entries",
    "official_seed_suite",
    "official_seeds_for_task",
    "private_eval_salt_policy",
    "seed_entry_for_task",
    "serious_seed_suite",
    "task_seed_plan",
]
