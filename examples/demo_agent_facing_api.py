"""Demo: agent-facing ChemWorld API."""

from __future__ import annotations

import json

import gymnasium as gym

import chemworld  # noqa: F401


def main() -> None:
    env = gym.make("ChemWorld", task_id="reaction-to-purification", seed=0)
    try:
        _, _ = env.reset(seed=0)
        print(env.unwrapped.task_prompt()["text"])
        print("\nAvailable actions at reset:")
        for entry in env.unwrapped.available_actions():
            print(f"- {entry['operation']}: {entry['schema']['required_fields']}")

        heat_schema = env.unwrapped.action_schema("heat")
        print("\nHeat schema:")
        print(json.dumps(heat_schema, indent=2, sort_keys=True))

        invalid = env.unwrapped.validate_action({"operation": "heat", "duration_s": 10.0})
        print("\nInvalid heat validation:")
        print(json.dumps(invalid, indent=2, sort_keys=True))

        action = {"operation": "add_solvent", "volume_L": 0.028, "solvent": 2}
        _, _, _, _, info = env.step(action)
        print("\nCampaign state after one step:")
        print(json.dumps(env.unwrapped.campaign_state(), indent=2, sort_keys=True))
        print("\nTool JSON view keys:", sorted(env.unwrapped.observation_view("tool_json")))
        print("Lab report:")
        print(env.unwrapped.observation_view("lab_report")["text"])
        print("Step cost:", info["cost"])
    finally:
        env.close()


if __name__ == "__main__":
    main()
