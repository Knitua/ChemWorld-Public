"""Fail-closed per-run resource accounting and enforceable limits."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from pathlib import Path
from time import perf_counter
from typing import Any

from chemworld.data.logging import to_builtin
from chemworld.physchem.mechanism_library import configuration_root

METHOD_RESOURCE_USAGE_VERSION = "chemworld-method-resource-usage-0.1"
METHOD_RESOURCE_LEDGER_VERSION = "chemworld-method-resource-ledger-0.1"
DEFAULT_RESOURCE_PROTOCOL_PATH = configuration_root() / "benchmark" / "resource_limits.json"

_AGENT_COUNTER_FIELDS = (
    "model_call_count",
    "input_token_count",
    "cached_input_token_count",
    "uncached_input_token_count",
    "output_token_count",
    "training_environment_step_count",
)
_AGENT_FLOAT_FIELDS = ("monetary_cost_usd", "cpu_time_s", "gpu_time_s")


class MethodResourceLimitError(RuntimeError):
    """Raised before a resource-over-budget run can be treated as valid."""


@dataclass(frozen=True)
class MethodResourceLimits:
    """Hard per-run limits; ``None`` means report-only for that resource."""

    operation_limit: int
    complete_experiment_limit: int | None = None
    wall_time_limit_s: float | None = None
    model_call_limit: int | None = None
    input_token_limit: int | None = None
    uncached_input_token_limit: int | None = None
    output_token_limit: int | None = None
    monetary_cost_limit_usd: float | None = None
    training_environment_step_limit: int | None = None
    cpu_time_limit_s: float | None = None
    gpu_time_limit_s: float | None = None
    checkpoint_complete_experiments: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        if self.operation_limit <= 0:
            raise ValueError("operation_limit must be positive")
        for name in (
            "complete_experiment_limit",
            "model_call_limit",
            "input_token_limit",
            "uncached_input_token_limit",
            "output_token_limit",
            "training_environment_step_limit",
        ):
            value = getattr(self, name)
            if value is not None and value < 0:
                raise ValueError(f"{name} must be non-negative")
        for name in (
            "wall_time_limit_s",
            "monetary_cost_limit_usd",
            "cpu_time_limit_s",
            "gpu_time_limit_s",
        ):
            value = getattr(self, name)
            if value is not None and (not math.isfinite(value) or value < 0.0):
                raise ValueError(f"{name} must be finite and non-negative")
        if tuple(sorted(set(self.checkpoint_complete_experiments))) != (
            self.checkpoint_complete_experiments
        ):
            raise ValueError("checkpoint_complete_experiments must be sorted and unique")
        if any(item <= 0 for item in self.checkpoint_complete_experiments):
            raise ValueError("checkpoint_complete_experiments must be positive")
        if (
            self.complete_experiment_limit is not None
            and self.checkpoint_complete_experiments
            and self.checkpoint_complete_experiments[-1] > self.complete_experiment_limit
        ):
            raise ValueError("checkpoints cannot exceed complete_experiment_limit")

    @classmethod
    def from_payload(
        cls,
        payload: Mapping[str, Any] | None,
        *,
        operation_limit: int,
    ) -> MethodResourceLimits:
        values = dict(payload or {})
        values.setdefault("operation_limit", operation_limit)
        checkpoints = values.get("checkpoint_complete_experiments", ())
        values["checkpoint_complete_experiments"] = tuple(int(item) for item in checkpoints)
        return cls(**values)


@dataclass
class MethodResourceLedger:
    """Cumulative resource ledger shared by every official runner adapter."""

    limits: MethodResourceLimits
    requires_online_model: bool = False
    started_at: float = field(default_factory=perf_counter)
    operation_count: int = 0
    complete_experiment_count: int = 0
    decision_wall_time_s: float = 0.0
    update_wall_time_s: float = 0.0
    agent_usage: dict[str, Any] = field(default_factory=dict)
    reached_checkpoints: list[int] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.requires_online_model and self.limits.model_call_limit is None:
            raise ValueError("online model ledgers require an explicit provider request limit")

    def record_decision(
        self,
        *,
        elapsed_s: float,
        agent_usage: Mapping[str, Any],
    ) -> None:
        if not math.isfinite(elapsed_s) or elapsed_s < 0.0:
            raise ValueError("decision elapsed time must be finite and non-negative")
        self.operation_count += 1
        self.decision_wall_time_s += elapsed_s
        self._accept_agent_usage(agent_usage)
        self._enforce()

    def reconcile_agent_usage(self, agent_usage: Mapping[str, Any]) -> None:
        """Accept cumulative usage learned after an asynchronous decision.

        A tool-using provider may expose exact token usage only after its
        experiment-level session ends.  The associated laboratory operation
        was already counted by :meth:`record_decision`, so reconciliation
        updates only provider counters and never creates a synthetic operation.
        """

        self._accept_agent_usage(agent_usage)
        self._enforce()

    def record_outcome(self, *, experiment_ended: bool, update_elapsed_s: float) -> None:
        if not math.isfinite(update_elapsed_s) or update_elapsed_s < 0.0:
            raise ValueError("update elapsed time must be finite and non-negative")
        self.update_wall_time_s += update_elapsed_s
        if experiment_ended:
            self.complete_experiment_count += 1
            if self.complete_experiment_count in self.limits.checkpoint_complete_experiments:
                self.reached_checkpoints.append(self.complete_experiment_count)
        self._enforce()

    def snapshot(self) -> dict[str, Any]:
        usage = self._normalized_usage(self.agent_usage)
        return {
            "schema_version": METHOD_RESOURCE_LEDGER_VERSION,
            "operation_count": self.operation_count,
            "complete_experiment_count": self.complete_experiment_count,
            "decision_wall_time_s": self.decision_wall_time_s,
            "update_wall_time_s": self.update_wall_time_s,
            "run_wall_time_s": perf_counter() - self.started_at,
            "reached_checkpoints": list(self.reached_checkpoints),
            "limits": to_builtin(asdict(self.limits)),
            "agent_usage": to_builtin(usage),
            "accounting_complete": bool(usage["accounting_complete"]),
            "provider_usage_pending": bool(usage["provider_usage_pending"]),
            "development_deferred_provider_usage": bool(
                self.requires_online_model
                and usage["provider_usage_pending"]
                and usage["in_flight_model_call_count"] == 1
            ),
            "development_monetary_accounting_incomplete": bool(
                self.requires_online_model
                and not usage["accounting_complete"]
                and usage["provider_usage_accounting_complete"]
                and not usage["monetary_accounting_complete"]
            ),
        }

    def _accept_agent_usage(self, payload: Mapping[str, Any]) -> None:
        usage = self._normalized_usage(payload)
        previous = self._normalized_usage(self.agent_usage)
        for name in (*_AGENT_COUNTER_FIELDS, *_AGENT_FLOAT_FIELDS):
            if usage[name] < previous[name]:
                raise ValueError(f"cumulative resource field decreased: {name}")
        if self.requires_online_model:
            deferred_experiment_session = bool(
                not usage["accounting_complete"]
                and usage["provider_usage_pending"]
                and usage["in_flight_model_call_count"] == 1
                and usage["provider_call_accounting_complete"]
                and not usage["provider_token_accounting_complete"]
                and not usage["monetary_accounting_complete"]
                and self.limits.model_call_limit is not None
                and self.limits.input_token_limit is not None
                and self.limits.output_token_limit is not None
                and self.limits.monetary_cost_limit_usd is None
            )
            development_unknown_pricing = bool(
                not usage["accounting_complete"]
                and usage["provider_usage_accounting_complete"]
                and usage["provider_call_accounting_complete"]
                and usage["provider_token_accounting_complete"]
                and not usage["monetary_accounting_complete"]
                and self.limits.monetary_cost_limit_usd is None
            )
            if (
                not usage["accounting_complete"]
                and not development_unknown_pricing
                and not deferred_experiment_session
            ):
                raise ValueError(
                    "online model resource accounting must be complete unless "
                    "provider call/token usage is explicitly complete and only "
                    "uncapped monetary accounting is incomplete, or exactly one "
                    "bounded experiment session has explicitly deferred usage"
                )
            provenance = usage["model_provenance"]
            required = {
                "provider",
                "model_id",
                "model_snapshot_or_access_date",
                "prompt_hash",
                "request_parameters",
                "tokenizer_or_provider_usage_source",
            }
            if not isinstance(provenance, dict) or not required.issubset(provenance):
                raise ValueError("online model usage requires provider/model/prompt provenance")
        self.agent_usage = usage

    def _normalized_usage(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        if not payload:
            payload = {
                "schema_version": METHOD_RESOURCE_USAGE_VERSION,
                "accounting_complete": not self.requires_online_model,
            }
        if payload.get("schema_version") != METHOD_RESOURCE_USAGE_VERSION:
            raise ValueError("unsupported method resource usage schema")
        accounting_complete = payload.get("accounting_complete") is True
        normalized: dict[str, Any] = {
            "schema_version": METHOD_RESOURCE_USAGE_VERSION,
            "accounting_complete": accounting_complete,
            "provider_usage_pending": payload.get("provider_usage_pending") is True,
            "provider_usage_accounting_complete": (
                payload.get(
                    "provider_usage_accounting_complete",
                    accounting_complete,
                )
                is True
            ),
            "provider_call_accounting_complete": (
                payload.get(
                    "provider_call_accounting_complete",
                    accounting_complete,
                )
                is True
            ),
            "provider_token_accounting_complete": (
                payload.get(
                    "provider_token_accounting_complete",
                    accounting_complete,
                )
                is True
            ),
            "provider_cache_accounting_complete": (
                payload.get(
                    "provider_cache_accounting_complete",
                    accounting_complete,
                )
                is True
            ),
            "monetary_accounting_complete": (
                payload.get(
                    "monetary_accounting_complete",
                    accounting_complete,
                )
                is True
            ),
            "usage_source": str(payload.get("usage_source", "unspecified")),
            "model_provenance": to_builtin(payload.get("model_provenance", {})),
        }
        in_flight = int(payload.get("in_flight_model_call_count", 0))
        if in_flight < 0:
            raise ValueError(
                "resource field must be non-negative: in_flight_model_call_count"
            )
        if normalized["provider_usage_pending"] != (in_flight > 0):
            raise ValueError(
                "provider_usage_pending must match in_flight_model_call_count"
            )
        normalized["in_flight_model_call_count"] = in_flight
        for name in _AGENT_COUNTER_FIELDS:
            raw_value = payload.get(name)
            if raw_value is None and name == "cached_input_token_count":
                raw_value = payload.get("prompt_cache_hit_tokens", 0)
            elif raw_value is None and name == "uncached_input_token_count":
                raw_value = payload.get("prompt_cache_miss_tokens", 0)
            counter_value = int(raw_value or 0)
            if counter_value < 0:
                raise ValueError(f"resource field must be non-negative: {name}")
            normalized[name] = counter_value
        if in_flight > normalized["model_call_count"]:
            raise ValueError(
                "in_flight_model_call_count cannot exceed model_call_count"
            )
        for name in _AGENT_FLOAT_FIELDS:
            float_value = float(payload.get(name, 0.0))
            if not math.isfinite(float_value) or float_value < 0.0:
                raise ValueError(f"resource field must be finite and non-negative: {name}")
            normalized[name] = float_value
        return normalized

    def _enforce(self) -> None:
        snapshot = self.snapshot()
        usage = snapshot["agent_usage"]
        checks = (
            ("operation_count", self.operation_count, self.limits.operation_limit),
            (
                "complete_experiment_count",
                self.complete_experiment_count,
                self.limits.complete_experiment_limit,
            ),
            ("run_wall_time_s", snapshot["run_wall_time_s"], self.limits.wall_time_limit_s),
            ("model_call_count", usage["model_call_count"], self.limits.model_call_limit),
            ("input_token_count", usage["input_token_count"], self.limits.input_token_limit),
            (
                "uncached_input_token_count",
                usage["uncached_input_token_count"],
                self.limits.uncached_input_token_limit,
            ),
            ("output_token_count", usage["output_token_count"], self.limits.output_token_limit),
            (
                "monetary_cost_usd",
                usage["monetary_cost_usd"],
                self.limits.monetary_cost_limit_usd,
            ),
            (
                "training_environment_step_count",
                usage["training_environment_step_count"],
                self.limits.training_environment_step_limit,
            ),
            ("cpu_time_s", usage["cpu_time_s"], self.limits.cpu_time_limit_s),
            ("gpu_time_s", usage["gpu_time_s"], self.limits.gpu_time_limit_s),
        )
        exceeded = [
            name for name, observed, limit in checks if limit is not None and observed > limit
        ]
        if exceeded:
            raise MethodResourceLimitError("method resource limit exceeded: " + ", ".join(exceeded))


def evaluation_resource_limits(
    protocol: Mapping[str, Any],
    *,
    operation_limit: int,
    requires_online_model: bool,
) -> MethodResourceLimits:
    """Translate the resource protocol into enforceable per-run limits."""

    evaluation = protocol["evaluation_budget"]
    resource_policy = protocol["resource_policy"]
    rl_limits = resource_policy["rl_hard_limits_per_task_training"]
    payload: dict[str, Any] = {
        "operation_limit": operation_limit,
        "complete_experiment_limit": int(evaluation["complete_experiments"]),
        "wall_time_limit_s": float(evaluation["wall_time_limit_s_per_run"]),
        "training_environment_step_limit": int(rl_limits["training_environment_steps"]),
        "gpu_time_limit_s": float(rl_limits["gpu_time_s"]),
        "checkpoint_complete_experiments": list(protocol["checkpoints"]),
    }
    if requires_online_model:
        llm_limits = resource_policy["llm_hard_limits_per_evaluation_run"]
        request_multiplier = int(llm_limits["provider_request_limit_per_operation"])
        if request_multiplier < 1:
            raise ValueError("provider_request_limit_per_operation must be positive")
        payload.update(
            {
                "model_call_limit": operation_limit * request_multiplier,
                "input_token_limit": int(llm_limits["input_tokens"]),
                "output_token_limit": int(llm_limits["output_tokens"]),
                "monetary_cost_limit_usd": float(llm_limits["monetary_cost_usd"]),
            }
        )
    return MethodResourceLimits.from_payload(payload, operation_limit=operation_limit)


def load_resource_protocol(path: str | Path = DEFAULT_RESOURCE_PROTOCOL_PATH) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("resource protocol must be a JSON object")
    return payload


__all__ = [
    "DEFAULT_RESOURCE_PROTOCOL_PATH",
    "METHOD_RESOURCE_LEDGER_VERSION",
    "METHOD_RESOURCE_USAGE_VERSION",
    "MethodResourceLedger",
    "MethodResourceLimitError",
    "MethodResourceLimits",
    "evaluation_resource_limits",
    "load_resource_protocol",
]
