"""Optional reinforcement-learning substrate with cycle-safe lazy exports."""

from __future__ import annotations

from typing import Any


def __getattr__(name: str) -> Any:
    if name in {"RLWorldAllocation", "TrainWorldFamilyWrapper", "build_rl_environment"}:
        from chemworld.rl import environment

        return getattr(environment, name)
    if name == "train_sb3_baseline":
        from chemworld.rl.training import train_sb3_baseline

        return train_sb3_baseline
    raise AttributeError(name)

__all__ = [
    "RLWorldAllocation",
    "TrainWorldFamilyWrapper",
    "build_rl_environment",
    "train_sb3_baseline",
]
