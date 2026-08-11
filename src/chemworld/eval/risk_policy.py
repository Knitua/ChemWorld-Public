"""Runtime-safe loading and binding of frozen benchmark risk policies."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from chemworld.physchem.mechanism_library import configuration_root
from chemworld.tasks import SERIOUS_TASK_IDS

RISK_COST_PROTOCOL_VERSION = "chemworld-risk-cost-protocol-0.1"
DEFAULT_RISK_COST_PROTOCOL_PATH = configuration_root() / "benchmark" / "risk_cost_vnext.json"


@dataclass(frozen=True)
class RiskCostTaskPolicy:
    task_id: str
    risk_limit: float
    process_cost_limit: float
    risk_semantics: str = "benchmark_operational_risk_budget_not_real_world_safety"

    def __post_init__(self) -> None:
        if self.task_id not in SERIOUS_TASK_IDS:
            raise ValueError(f"unsupported serious task: {self.task_id}")
        if not math.isfinite(self.risk_limit) or not 0.0 < self.risk_limit < 1.0:
            raise ValueError("risk_limit must be finite and in (0, 1)")
        if not math.isfinite(self.process_cost_limit) or self.process_cost_limit <= 0.0:
            raise ValueError("process_cost_limit must be finite and positive")
        if self.risk_semantics != "benchmark_operational_risk_budget_not_real_world_safety":
            raise ValueError("risk policy must explicitly reject real-world safety semantics")

    @classmethod
    def from_protocol(
        cls,
        task_id: str,
        protocol: dict[str, Any],
    ) -> RiskCostTaskPolicy:
        if protocol.get("schema_version") != RISK_COST_PROTOCOL_VERSION:
            raise ValueError("unsupported risk-cost protocol schema")
        tasks = protocol.get("tasks", {})
        if not isinstance(tasks, dict) or not isinstance(tasks.get(task_id), dict):
            raise ValueError(f"risk-cost protocol is missing task {task_id!r}")
        payload = tasks[task_id]
        return cls(
            task_id=task_id,
            risk_limit=float(payload["risk_limit"]),
            process_cost_limit=float(payload["process_cost_limit"]),
            risk_semantics=str(protocol.get("risk_semantics", "")),
        )

    def task_info_overlay(self) -> dict[str, Any]:
        """Return the public policy that a vNext runner gives every method."""

        return {
            "safety_limit": self.risk_limit,
            "risk_limit": self.risk_limit,
            "risk_limit_semantics": self.risk_semantics,
            "risk_aggregation": "max_operation_risk_per_experiment",
            "process_cost_limit": self.process_cost_limit,
        }

    @property
    def policy_hash(self) -> str:
        payload = {"task_id": self.task_id, **self.task_info_overlay()}
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()


def load_risk_cost_protocol(
    path: str | Path = DEFAULT_RISK_COST_PROTOCOL_PATH,
) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("risk-cost protocol must be a JSON object")
    return payload


__all__ = [
    "DEFAULT_RISK_COST_PROTOCOL_PATH",
    "RISK_COST_PROTOCOL_VERSION",
    "RiskCostTaskPolicy",
    "load_risk_cost_protocol",
]
