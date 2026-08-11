"""Demo: RL-friendly vector observation wrapper."""

from __future__ import annotations

import gymnasium as gym
import numpy as np

import chemworld  # noqa: F401
from chemworld.wrappers import RLObservationWrapper


def main() -> None:
    env = RLObservationWrapper(gym.make("ChemWorld", task_id="reaction-to-assay", seed=0))
    try:
        observation, info = env.reset(seed=0)
        print("Reset vector shape:", observation.shape)
        print("Finite:", bool(np.all(np.isfinite(observation))))
        print("Initial mask sum:", float(info["observation_mask"].sum()))

        observation, reward, terminated, truncated, info = env.step(
            {"operation": "add_solvent", "volume_L": 0.028, "solvent": 2}
        )
        print("Step vector shape:", observation.shape)
        print("Reward:", reward, "terminated:", terminated, "truncated:", truncated)
        print("Cost signal:", info["cost_signal"])
    finally:
        env.close()


if __name__ == "__main__":
    main()
