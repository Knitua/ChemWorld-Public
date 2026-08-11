"""Agent interface used by ChemWorld runners."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from chemworld.agents.interaction import InteractionCapabilities


@dataclass(frozen=True)
class HistoryRecord:
    step: int
    action: dict[str, Any]
    observation: dict[str, float | None]
    reward: float
    info: dict[str, Any]
    public_view: dict[str, Any] = field(default_factory=dict)
    decision_context: dict[str, Any] = field(default_factory=dict)
    decision_audit: dict[str, Any] = field(default_factory=dict)
    event_type: str = "operation_result"
    method_resources: dict[str, Any] = field(default_factory=dict)


class Agent(Protocol):
    """Minimal interface for benchmark agents."""

    name: str

    def reset(self, task_info: dict[str, Any], seed: int) -> None:
        """Prepare the agent for one task instance."""

    def act(self, history: list[HistoryRecord]) -> dict[str, Any]:
        """Choose the next experiment action."""

    def update(
        self,
        action: dict[str, Any],
        observation: dict[str, float | None],
        reward: float,
        info: dict[str, Any],
    ) -> None:
        """Receive feedback after an experiment."""

    def manifest(self) -> dict[str, Any]:
        """Return reproducibility metadata."""

    def method_resource_usage(self) -> dict[str, Any]:
        """Return cumulative external-model and training resource usage."""


class BaseAgent:
    """Convenience base class for official baselines."""

    name = "base"

    def reset(self, task_info: dict[str, Any], seed: int) -> None:
        self.task_info = task_info
        self.seed = seed

    def update(
        self,
        action: dict[str, Any],
        observation: dict[str, float | None],
        reward: float,
        info: dict[str, Any],
    ) -> None:
        del action, observation, reward, info

    def manifest(self) -> dict[str, Any]:
        capabilities = self.interaction_capabilities()
        return {
            "agent_name": self.name,
            "agent_family": self.__class__.__name__,
            "seed": getattr(self, "seed", None),
            "interaction_capabilities": capabilities.to_dict(),
        }

    def method_resource_usage(self) -> dict[str, Any]:
        """Declare zero external usage for deterministic in-process agents.

        Live model and training adapters must override this method with complete,
        cumulative provider/token/cost or training-compute accounting.
        """

        return {
            "schema_version": "chemworld-method-resource-usage-0.1",
            "accounting_complete": True,
            "usage_source": "no_external_model_or_training_runtime",
            "model_call_count": 0,
            "input_token_count": 0,
            "output_token_count": 0,
            "monetary_cost_usd": 0.0,
            "training_environment_step_count": 0,
            "cpu_time_s": 0.0,
            "gpu_time_s": 0.0,
            "model_provenance": {},
        }

    def interaction_capabilities(self) -> InteractionCapabilities:
        return InteractionCapabilities()
