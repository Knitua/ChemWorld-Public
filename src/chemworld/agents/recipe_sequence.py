"""Utilities for agents that plan terminal recipes but execute event actions."""

from __future__ import annotations

import math
from typing import Any

from chemworld.agents.base import BaseAgent, HistoryRecord
from chemworld.agents.interaction import InteractionCapabilities
from chemworld.world.recipes import compile_recipe

DEFAULT_RECIPE_EVENT_COUNT = 6


class RecipeSequenceMixin(BaseAgent):
    """Queue event-level operations for one recipe-style recommendation."""

    def reset(self, task_info: dict[str, Any], seed: int) -> None:
        super().reset(task_info, seed)
        self._pending_events: list[dict[str, Any]] = []
        self._active_recipe: dict[str, Any] | None = None
        self._active_recipe_peak_safety_risk = 0.0
        self._recipe_history: list[HistoryRecord] = []

    def _pop_pending_event(self) -> dict[str, Any] | None:
        if self._pending_events:
            return dict(self._pending_events.pop(0))
        return None

    def _start_recipe(self, recipe: dict[str, Any]) -> dict[str, Any]:
        self._active_recipe = dict(recipe)
        self._active_recipe_peak_safety_risk = 0.0
        self._pending_events = compile_recipe(recipe, task_info=self.task_info)
        event = self._pop_pending_event()
        if event is None:
            raise RuntimeError("compile_recipe returned no executable events")
        return event

    def update(
        self,
        action: dict[str, Any],
        observation: dict[str, float | None],
        reward: float,
        info: dict[str, Any],
    ) -> None:
        observed_risk = observation.get("safety_risk")
        if (
            self._active_recipe is not None
            and isinstance(observed_risk, int | float)
            and math.isfinite(float(observed_risk))
        ):
            self._active_recipe_peak_safety_risk = max(
                self._active_recipe_peak_safety_risk,
                float(observed_risk),
            )
        if (
            self._active_recipe is not None
            and action.get("operation") == "measure"
            and action.get("instrument") == "final_assay"
        ):
            terminal_observation = dict(observation)
            terminal_observation["experiment_peak_safety_risk"] = (
                self._active_recipe_peak_safety_risk
            )
            terminal_info = dict(info)
            terminal_info["experiment_peak_safety_risk"] = (
                self._active_recipe_peak_safety_risk
            )
            terminal_info["experiment_risk_limit"] = self.task_info.get("safety_limit")
            self._recipe_history.append(
                HistoryRecord(
                    step=len(self._recipe_history) + 1,
                    action=dict(self._active_recipe),
                    observation=terminal_observation,
                    reward=float(reward),
                    info=terminal_info,
                )
            )
            self._active_recipe = None
            self._active_recipe_peak_safety_risk = 0.0

    def interaction_capabilities(self) -> InteractionCapabilities:
        return InteractionCapabilities(
            decision_scope="experiment_recipe",
            consumes_intermediate_observations=False,
            consumes_spectra=False,
            adapts_within_experiment=False,
            adapts_across_experiments=False,
            emits_structured_decision_audit=False,
        )
