"""Gymnasium environment registration."""

from __future__ import annotations

from gymnasium.envs.registration import register, registry

ENV_ID = "ChemWorld"
ENV_IDS = (ENV_ID,)


def register_envs() -> None:
    """Register ChemWorld environments with Gymnasium."""

    if ENV_ID not in registry:
        register(
            id=ENV_ID,
            entry_point="chemworld.envs.chemworld_env:ChemWorldEnv",
            max_episode_steps=None,
        )
