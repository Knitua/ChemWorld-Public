"""Run one explicit event-sequence experiment in ChemWorld."""

from __future__ import annotations

import json

import gymnasium as gym

import chemworld  # noqa: F401


def main() -> None:
    env = gym.make("ChemWorld", world_split="public-dev", budget=8, seed=7)
    try:
        observation, task_info = env.reset(seed=7)
        print(json.dumps({"task": task_info["scenario_id"], "initial": _flat(observation)}))

        actions = [
            {"operation": "add_solvent", "volume_L": 0.030, "solvent": 2},
            {"operation": "add_reagent", "amount_mol": 0.010},
            {"operation": "add_catalyst", "catalyst_amount_mol": 0.00025, "catalyst": 1},
            {
                "operation": "heat",
                "target_temperature_K": 388.0,
                "duration_s": 1500.0,
                "stirring_speed_rpm": 720.0,
            },
            {"operation": "measure", "instrument": "hplc"},
            {"operation": "wait", "duration_s": 600.0, "stirring_speed_rpm": 720.0},
            {"operation": "terminate"},
            {"operation": "measure", "instrument": "final_assay"},
        ]

        for action in actions:
            observation, reward, _, truncated, info = env.step(action)
            print(
                json.dumps(
                    {
                        "step": info["step"],
                        "operation": info["operation_type"],
                        "reward": round(reward, 4),
                        "observation": _flat(observation),
                        "flags": info["constraint_flags"],
                    },
                    sort_keys=True,
                )
            )
            if truncated:
                break
    finally:
        env.close()


def _flat(observation: dict[str, object]) -> dict[str, float]:
    return {
        key: round(float(value.reshape(-1)[0]), 4)
        for key, value in observation.items()
    }


if __name__ == "__main__":
    main()
