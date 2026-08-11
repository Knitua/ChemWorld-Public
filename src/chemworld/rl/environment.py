"""Train-only world-family sampling and operation-level RL adapters."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast

import gymnasium as gym
import numpy as np

import chemworld  # noqa: F401
from chemworld.world.world_family import axes_for_task
from chemworld.wrappers import (
    ConditionalHybridActionWrapper,
    RLControlObservationWrapper,
    RLObservationWrapper,
    RLTrainingRewardWrapper,
)

AllocationName = Literal["train", "dev", "bench"]


@dataclass(frozen=True)
class RLWorldAllocation:
    """A frozen set of seeds and executable one-axis world-family cells."""

    name: AllocationName
    task_id: str
    base_seeds: tuple[int, ...]
    cells: tuple[tuple[str, str, float], ...]
    namespace_id: str | None = None

    def __post_init__(self) -> None:
        if not self.base_seeds or len(set(self.base_seeds)) != len(self.base_seeds):
            raise ValueError("world allocation seeds must be non-empty and unique")
        task_axes = {axis.axis_id for axis in axes_for_task(self.task_id)}
        if not self.cells or any(axis_id not in task_axes for axis_id, _, _ in self.cells):
            raise ValueError("world allocation contains a missing or cross-task axis")
        if any(not np.isfinite(severity) or severity == 0.0 for _, _, severity in self.cells):
            raise ValueError("world allocation severity must be finite and non-zero")
        if self.namespace_id is not None and not self.namespace_id.strip():
            raise ValueError("world allocation namespace_id must be non-empty when supplied")

    @classmethod
    def from_protocol(
        cls,
        protocol: dict[str, Any],
        *,
        task_id: str,
        name: AllocationName,
    ) -> RLWorldAllocation:
        payload = protocol["world_family_allocation"][name]
        seed_range = payload["base_seeds"]
        seeds = tuple(range(int(seed_range["start"]), int(seed_range["stop_inclusive"]) + 1))
        cells = tuple(
            (axis.axis_id, mode, float(severity))
            for axis in axes_for_task(task_id)
            for mode, severities in payload["cells"].items()
            for severity in severities
        )
        namespace_id = payload.get("namespace_id")
        return cls(
            name=name,
            task_id=task_id,
            base_seeds=seeds,
            cells=cells,
            namespace_id=str(namespace_id) if namespace_id is not None else None,
        )

    def public_manifest(self) -> dict[str, Any]:
        payload = {
            "name": self.name,
            "task_id": self.task_id,
            "seed_count": len(self.base_seeds),
            "seed_min": min(self.base_seeds),
            "seed_max": max(self.base_seeds),
            "cell_count": len(self.cells),
            "modes": sorted({mode for _, mode, _ in self.cells}),
        }
        if self.namespace_id is not None:
            payload["namespace_id"] = self.namespace_id
        return payload


class TrainWorldFamilyWrapper(gym.Wrapper[Any, Any, Any, Any]):
    """Resample only from one frozen allocation on every reset."""

    def __init__(
        self,
        env: gym.Env[Any, Any],
        *,
        allocation: RLWorldAllocation,
        sampler_seed: int,
    ) -> None:
        super().__init__(env)
        if allocation.name == "bench":
            raise ValueError("Bench allocation cannot be attached to a training wrapper")
        self.allocation = allocation
        self._sampler = np.random.default_rng(sampler_seed)
        self._last_cell: dict[str, Any] | None = None

    def reset(self, **kwargs: Any) -> tuple[Any, dict[str, Any]]:
        base = cast(Any, self.env.unwrapped)
        world_seed = int(self._sampler.choice(self.allocation.base_seeds))
        axis_id, mode, severity = self.allocation.cells[
            int(self._sampler.integers(0, len(self.allocation.cells)))
        ]
        intervention = {"axis_id": axis_id, "mode": mode, "severity": severity}
        base.world_interventions = (intervention,)
        self._last_cell = {
            "allocation": self.allocation.name,
            "world_seed": world_seed,
            **intervention,
        }
        kwargs.pop("seed", None)
        observation, info = self.env.reset(seed=world_seed, **kwargs)
        payload = dict(info)
        cell_bytes = json.dumps(self._last_cell, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
        payload["rl_world_cell"] = {
            "allocation": self.allocation.name,
            "opaque_cell_id": hashlib.sha256(cell_bytes).hexdigest()[:16],
            "axis_identity_visible": False,
        }
        return observation, payload


def load_rl_protocol(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("RL protocol must be a JSON object")
    return payload


def build_rl_environment(
    *,
    task_id: str,
    allocation: RLWorldAllocation,
    sampler_seed: int,
    operation_budget: int | None = None,
    training_reward: bool = False,
) -> gym.Env[np.ndarray, np.ndarray]:
    """Construct the conditional hybrid contract through an SB3 Box latent adapter."""

    if allocation.task_id != task_id:
        raise ValueError("allocation task does not match environment task")
    kwargs: dict[str, Any] = {"task_id": task_id, "seed": allocation.base_seeds[0]}
    if operation_budget is not None:
        kwargs["budget_override"] = int(operation_budget)
        kwargs["episode_mode_override"] = "campaign"
    env: gym.Env[Any, Any] = gym.make("ChemWorld", **kwargs)
    env = TrainWorldFamilyWrapper(env, allocation=allocation, sampler_seed=sampler_seed)
    env = ConditionalHybridActionWrapper(env)
    env = RLObservationWrapper(env, include_mask=True, include_cost=True)
    env = RLControlObservationWrapper(env)
    if training_reward:
        env = RLTrainingRewardWrapper(env)
    return env


__all__ = [
    "RLWorldAllocation",
    "TrainWorldFamilyWrapper",
    "build_rl_environment",
    "load_rl_protocol",
]
