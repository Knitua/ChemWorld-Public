"""Observable, provider-free agent runs for the local browser lab."""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from time import monotonic
from typing import Any

from chemworld.agents.base import HistoryRecord
from chemworld.data.logging import to_builtin
from chemworld.eval.runner import make_agent, run_agent
from chemworld.lab.limits import LabCapacityError
from chemworld.tasks import get_task

_AGENT_CARDS: tuple[dict[str, Any], ...] = (
    {
        "agent_id": "scripted_chemistry",
        "title": "Scripted Chemistry",
        "family": "Reference recipe",
        "summary": "按任务合同执行确定性的完整实验路径，适合第一次观察。",
        "behavior": "deterministic",
        "recommended": True,
        "uses_model": False,
    },
    {
        "agent_id": "random",
        "title": "Random Recipe",
        "family": "Stochastic baseline",
        "summary": "在任务配方空间中随机采样完整实验，用于建立无优化基线。",
        "behavior": "seeded stochastic",
        "recommended": False,
        "uses_model": False,
    },
    {
        "agent_id": "lhs",
        "title": "Latin Hypercube",
        "family": "Design of experiments",
        "summary": "使用拉丁超立方覆盖连续条件，强调空间覆盖而不是局部寻优。",
        "behavior": "seeded design",
        "recommended": False,
        "uses_model": False,
    },
    {
        "agent_id": "greedy",
        "title": "Greedy Local Search",
        "family": "Adaptive search",
        "summary": "围绕历史最佳实验进行局部扰动，并保留少量探索。",
        "behavior": "adaptive",
        "recommended": False,
        "uses_model": False,
    },
    {
        "agent_id": "gp_bo",
        "title": "Gaussian Process BO",
        "family": "Bayesian optimization",
        "summary": "以高斯过程代理模型选择后续实验，展示跨实验适应。",
        "behavior": "adaptive surrogate",
        "recommended": False,
        "uses_model": False,
    },
    {
        "agent_id": "safe_gp_bo",
        "title": "Safety-constrained BO",
        "family": "Constrained optimization",
        "summary": "在公开风险约束下进行贝叶斯优化，显式权衡信息与安全。",
        "behavior": "risk-aware adaptive",
        "recommended": False,
        "uses_model": False,
    },
    {
        "agent_id": "tool_using_llm_stub",
        "title": "Tool-agent Stub",
        "family": "Agent interface demo",
        "summary": "不调用模型的工具 Agent，用于检查 Agent 接口和轨迹字段。",
        "behavior": "deterministic stub",
        "recommended": False,
        "uses_model": False,
    },
    {
        "agent_id": "llm_replay",
        "title": "LLM Trace Replay",
        "family": "Offline model replay",
        "summary": "回放内置的公开模型式决策轨迹，同时显示理由、记忆和验证结果。",
        "behavior": "deterministic replay",
        "recommended": False,
        "uses_model": False,
    },
)

_APPARATUS_LABELS = {
    "batch": "批式反应器",
    "separation": "液液分离系统",
    "crystallization": "冷却结晶系统",
    "distillation": "蒸馏与馏分收集",
    "flow": "连续流反应器",
    "electrochemical": "电化学反应池",
}


class AgentRunCancelledError(RuntimeError):
    """Internal signal used to stop a background run at a step boundary."""


def agent_catalog() -> list[dict[str, Any]]:
    """Return the deliberately provider-free strategies exposed in the browser."""

    return [dict(card) for card in _AGENT_CARDS]


def _apparatus_family(operations: tuple[str, ...]) -> str:
    operation_set = set(operations)
    if "electrolyze" in operation_set:
        return "electrochemical"
    if "run_flow" in operation_set:
        return "flow"
    if "cool_crystallize" in operation_set:
        return "crystallization"
    if "distill" in operation_set:
        return "distillation"
    if "separate_phase" in operation_set:
        return "separation"
    return "batch"


def _downsample(
    x_values: list[Any],
    y_values: list[Any],
    limit: int = 180,
) -> tuple[list[Any], list[Any]]:
    count = min(len(x_values), len(y_values))
    if count <= limit:
        return x_values[:count], y_values[:count]
    indices = sorted({round(index * (count - 1) / (limit - 1)) for index in range(limit)})
    return [x_values[index] for index in indices], [y_values[index] for index in indices]


def _chart(signal: dict[str, Any]) -> dict[str, Any] | None:
    axes = (
        ("time_min", "intensity", "Retention time / min", "Intensity"),
        ("wavelength_nm", "absorbance", "Wavelength / nm", "Absorbance"),
        ("wavenumber_cm-1", "transmittance", "Wavenumber / cm⁻¹", "Transmittance"),
        ("chemical_shift_ppm", "intensity", "Chemical shift / ppm", "Intensity"),
        ("potential_V", "current_mA", "Potential / V", "Current / mA"),
    )
    for x_key, y_key, x_label, y_label in axes:
        x_values, y_values = signal.get(x_key), signal.get(y_key)
        if isinstance(x_values, list) and isinstance(y_values, list) and x_values and y_values:
            x_values, y_values = _downsample(x_values, y_values)
            return {
                "kind": signal.get("kind"),
                "instrument": signal.get("instrument_id"),
                "x_label": x_label,
                "y_label": y_label,
                "x": to_builtin(x_values),
                "y": to_builtin(y_values),
                "peaks": to_builtin(list(signal.get("peaks") or [])[:12]),
            }
    return None


def _spectra(raw_signal: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_signal, dict):
        return []
    charts: list[dict[str, Any]] = []
    direct = _chart(raw_signal)
    if direct is not None:
        charts.append(direct)
    nested = raw_signal.get("spectra")
    if isinstance(nested, dict):
        for instrument, signal in nested.items():
            if not isinstance(signal, dict):
                continue
            item = _chart({"instrument_id": instrument, **signal})
            if item is not None:
                charts.append(item)
            if len(charts) >= 5:
                break
    return charts


def _record_payload(record: HistoryRecord, trace: list[dict[str, Any]]) -> dict[str, Any]:
    lab_report = dict(record.public_view.get("lab_report") or {})
    tool_view = dict(record.public_view.get("tool_json") or {})
    info = record.info
    state_delta = dict(info.get("state_delta_summary") or {})
    return {
        "step": record.step,
        "action": to_builtin(record.action),
        "event_type": record.event_type,
        "reward": float(record.reward),
        "transaction_status": str(info.get("transaction_status") or "unknown"),
        "status": str(lab_report.get("status") or info.get("error_message") or ""),
        "report_text": str(lab_report.get("text") or ""),
        "recovery_suggestion": lab_report.get("recovery_suggestion"),
        "next_action_hints": to_builtin(lab_report.get("next_action_hints") or []),
        "visible_metrics": to_builtin(lab_report.get("visible_metrics") or {}),
        "constraint_flags": to_builtin(info.get("constraint_flags") or {}),
        "observed_keys": to_builtin(info.get("observed_keys") or []),
        "leaderboard_score": to_builtin(info.get("leaderboard_score")),
        "instrument": info.get("instrument"),
        "state_delta": {
            "delta_time_s": float(state_delta.get("delta_time_s", 0.0)),
            "delta_volume_L": float(state_delta.get("delta_volume_L", 0.0)),
            "delta_temperature_K": float(state_delta.get("delta_temperature_K", 0.0)),
            "delta_risk": float(state_delta.get("delta_risk", info.get("risk_delta", 0.0))),
            "delta_cost": float(state_delta.get("delta_cost", info.get("cost_delta", 0.0))),
        },
        "decision_context": to_builtin(record.decision_context),
        "decision_audit": to_builtin(record.decision_audit),
        "method_resources": to_builtin(record.method_resources),
        "agent_trace": to_builtin(trace[-1] if trace else {}),
        "spectra": _spectra(tool_view.get("raw_signal")),
        "processed_estimate": to_builtin(tool_view.get("processed_estimate") or {}),
        "uncertainty": to_builtin(tool_view.get("uncertainty") or {}),
    }


@dataclass
class AgentRun:
    """One background official-runner episode with step-boundary controls."""

    task_id: str
    agent_id: str
    seed: int
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    status: str = "ready"
    records: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None
    created_at: float = field(default_factory=monotonic)
    _continuous: bool = False
    _permits: int = 0
    _cancelled: bool = False
    _thread: threading.Thread | None = None
    _condition: threading.Condition = field(default_factory=threading.Condition, repr=False)

    def __post_init__(self) -> None:
        public_agent_ids = {str(card["agent_id"]) for card in _AGENT_CARDS}
        if self.agent_id not in public_agent_ids:
            raise ValueError(f"agent is not exposed in the provider-free Lab: {self.agent_id}")
        task = get_task(self.task_id)
        make_agent(self.agent_id)
        self._task_budget = task.budget
        self._apparatus_family = _apparatus_family(task.allowed_operations)

    def step(self) -> None:
        with self._condition:
            self._ensure_startable()
            self._continuous = False
            self._permits += 1
            self._start_worker_locked()
            self.status = "running"
            self._condition.notify_all()

    def run(self) -> None:
        with self._condition:
            self._ensure_startable()
            self._continuous = True
            self._start_worker_locked()
            self.status = "running"
            self._condition.notify_all()

    def pause(self) -> None:
        with self._condition:
            if self.status in {"running", "paused"}:
                self._continuous = False
                self._permits = 0

    def cancel(self) -> None:
        with self._condition:
            if self.status not in {"completed", "failed", "cancelled"}:
                self._cancelled = True
                self.status = "cancelled"
                self._condition.notify_all()

    def worker_active(self) -> bool:
        """Return whether this run owns a live background worker."""

        with self._condition:
            return self._thread is not None and self._thread.is_alive()

    def _ensure_startable(self) -> None:
        if self.status in {"completed", "failed", "cancelled"}:
            raise ValueError(f"agent run is already {self.status}")

    def _start_worker_locked(self) -> None:
        if self._thread is None:
            self._thread = threading.Thread(target=self._work, daemon=True)
            self._thread.start()

    def _work(self) -> None:
        try:
            agent = make_agent(self.agent_id)
            run_agent(
                env_id="ChemWorld",
                agent=agent,
                world_split="public-dev",
                budget=self._task_budget,
                objective="balanced",
                seed=self.seed,
                agent_seed=self.seed,
                task_id=self.task_id,
                step_callback=self._on_step,
                method_resource_limits={
                    "operation_limit": self._task_budget,
                    "complete_experiment_limit": self._task_budget,
                },
            )
            with self._condition:
                if not self._cancelled:
                    self.status = "completed"
                self._condition.notify_all()
        except AgentRunCancelledError:
            pass
        except Exception as exc:  # pragma: no cover - exercised through failure state
            with self._condition:
                self.status = "failed"
                self.error = f"{type(exc).__name__}: {exc}"
                self._condition.notify_all()

    def _on_step(self, record: HistoryRecord, trace: list[dict[str, Any]]) -> None:
        payload = _record_payload(record, trace)
        with self._condition:
            if self._cancelled:
                raise AgentRunCancelledError()
            self.records.append(payload)
            if record.event_type == "experiment_end":
                return
            if self._continuous:
                return
            if self._permits > 0:
                self._permits -= 1
            while not self._continuous and self._permits <= 0 and not self._cancelled:
                self.status = "paused"
                self._condition.notify_all()
                self._condition.wait()
            if self._cancelled:
                raise AgentRunCancelledError()
            self.status = "running"

    def state(self) -> dict[str, Any]:
        with self._condition:
            latest = self.records[-1] if self.records else None
            visible = dict(latest.get("visible_metrics") or {}) if latest else {}
            score = latest.get("leaderboard_score") if latest else None
            if score is None:
                score = visible.get("score")
            operations = [
                str(item.get("action", {}).get("operation") or "")
                for item in self.records
            ]
            return {
                "run_id": self.run_id,
                "task_id": self.task_id,
                "agent_id": self.agent_id,
                "seed": self.seed,
                "status": self.status,
                "error": self.error,
                "step_count": len(self.records),
                "budget": self._task_budget,
                "score": score,
                "cost": visible.get("cost", 0.0),
                "safety_risk": visible.get("safety_risk", 0.0),
                "runtime_s": (
                    float(latest.get("method_resources", {}).get("run_wall_time_s", 0.0))
                    if latest
                    else 0.0
                ),
                "apparatus": {
                    "family": self._apparatus_family,
                    "label": _APPARATUS_LABELS[self._apparatus_family],
                    "phase_active": any(
                        item in {"add_phase", "add_extractant", "mix", "settle", "separate_phase"}
                        for item in operations
                    ),
                    "solid_active": any(
                        item in {"seed_crystals", "cool_crystallize", "filter_crystals"}
                        for item in operations
                    ),
                },
                "records": list(self.records),
            }


@dataclass
class AgentComparison:
    """A same-task, same-seed exploratory comparison of local strategies."""

    task_id: str
    agent_ids: list[str]
    seed: int
    run_ids: list[str]
    comparison_id: str = field(default_factory=lambda: uuid.uuid4().hex)


class AgentRunManager:
    """Thread-safe registry for observable agent runs and comparisons."""

    def __init__(
        self,
        *,
        max_runs: int | None = None,
        max_concurrent_runs: int | None = None,
        run_ttl_s: float | None = None,
    ) -> None:
        if max_runs is not None and max_runs < 1:
            raise ValueError("max_runs must be positive")
        if max_concurrent_runs is not None and max_concurrent_runs < 1:
            raise ValueError("max_concurrent_runs must be positive")
        if run_ttl_s is not None and run_ttl_s <= 0:
            raise ValueError("run_ttl_s must be positive")
        self._max_runs = max_runs
        self._max_concurrent_runs = max_concurrent_runs
        self._run_ttl_s = run_ttl_s
        self._runs: dict[str, AgentRun] = {}
        self._comparisons: dict[str, AgentComparison] = {}
        self._last_access: dict[str, float] = {}
        self._lock = threading.RLock()

    def create(self, task_id: str, agent_id: str, seed: int) -> AgentRun:
        with self._lock:
            self._prune_locked(monotonic())
            self._make_room_locked(1)
            run = AgentRun(task_id=task_id, agent_id=agent_id, seed=seed)
            self._runs[run.run_id] = run
            self._last_access[run.run_id] = monotonic()
        return run

    def get(self, run_id: str) -> AgentRun:
        with self._lock:
            self._prune_locked(monotonic())
            try:
                run = self._runs[run_id]
            except KeyError as exc:
                raise KeyError(f"unknown agent run: {run_id}") from exc
            self._last_access[run_id] = monotonic()
            return run

    def command(self, run_id: str, command: str) -> AgentRun:
        """Apply a bounded public control command to a run."""

        run = self.get(run_id)
        commands = {
            "step": run.step,
            "run": run.run,
            "pause": run.pause,
            "cancel": run.cancel,
        }
        if command not in commands:
            raise ValueError("command must be step, run, pause, or cancel")
        with self._lock:
            if (
                command in {"step", "run"}
                and not run.worker_active()
                and self._max_concurrent_runs is not None
                and self._active_workers_locked() >= self._max_concurrent_runs
            ):
                raise LabCapacityError("public Lab agent capacity is temporarily full")
            commands[command]()
        return run

    def compare(self, task_id: str, agent_ids: list[str], seed: int) -> AgentComparison:
        unique = list(dict.fromkeys(agent_ids))
        if not 2 <= len(unique) <= 4:
            raise ValueError("comparison requires two to four distinct agents")
        with self._lock:
            self._prune_locked(monotonic())
            if (
                self._max_concurrent_runs is not None
                and self._active_workers_locked() + len(unique) > self._max_concurrent_runs
            ):
                raise LabCapacityError("public Lab comparison capacity is temporarily full")
            self._make_room_locked(len(unique))
            runs = [AgentRun(task_id, agent_id, seed) for agent_id in unique]
            accessed_at = monotonic()
            for run in runs:
                self._runs[run.run_id] = run
                self._last_access[run.run_id] = accessed_at
            comparison = AgentComparison(task_id, unique, seed, [run.run_id for run in runs])
            self._comparisons[comparison.comparison_id] = comparison
            for run in runs:
                run.run()
        return comparison

    def _active_workers_locked(self) -> int:
        return sum(run.worker_active() for run in self._runs.values())

    def _terminal_ids_locked(self) -> list[str]:
        terminal = {"completed", "failed", "cancelled"}
        return sorted(
            (
                run_id
                for run_id, run in self._runs.items()
                if run.state()["status"] in terminal and not run.worker_active()
            ),
            key=lambda run_id: self._last_access.get(run_id, 0.0),
        )

    def _drop_locked(self, run_id: str) -> None:
        self._runs.pop(run_id, None)
        self._last_access.pop(run_id, None)
        self._comparisons = {
            comparison_id: comparison
            for comparison_id, comparison in self._comparisons.items()
            if run_id not in comparison.run_ids
        }

    def _prune_locked(self, now: float) -> None:
        if self._run_ttl_s is None:
            return
        stale_ids = [
            run_id
            for run_id, accessed_at in self._last_access.items()
            if now - accessed_at >= self._run_ttl_s
        ]
        for run_id in stale_ids:
            run = self._runs[run_id]
            run.cancel()
            if not run.worker_active():
                self._drop_locked(run_id)

    def _make_room_locked(self, required: int) -> None:
        if self._max_runs is None:
            return
        for run_id in self._terminal_ids_locked():
            if len(self._runs) + required <= self._max_runs:
                break
            self._drop_locked(run_id)
        if len(self._runs) + required > self._max_runs:
            raise LabCapacityError("public Lab run registry is temporarily full")

    def comparison_state(self, comparison_id: str) -> dict[str, Any]:
        with self._lock:
            try:
                comparison = self._comparisons[comparison_id]
            except KeyError as exc:
                raise KeyError(f"unknown agent comparison: {comparison_id}") from exc
        runs = [self.get(run_id).state() for run_id in comparison.run_ids]
        return {
            "comparison_id": comparison.comparison_id,
            "task_id": comparison.task_id,
            "seed": comparison.seed,
            "status": (
                "completed"
                if all(run["status"] == "completed" for run in runs)
                else "failed"
                if any(run["status"] == "failed" for run in runs)
                else "running"
            ),
            "runs": [
                {
                    key: run[key]
                    for key in (
                        "run_id",
                        "agent_id",
                        "status",
                        "step_count",
                        "budget",
                        "score",
                        "cost",
                        "safety_risk",
                        "runtime_s",
                        "error",
                    )
                }
                for run in runs
            ],
        }

    def close_all(self) -> None:
        with self._lock:
            runs = list(self._runs.values())
            self._runs.clear()
            self._comparisons.clear()
            self._last_access.clear()
        for run in runs:
            run.cancel()


__all__ = ["AgentRun", "AgentRunManager", "agent_catalog"]
