"""Stateful, provider-free sessions for the public browser lab."""

from __future__ import annotations

import threading
import uuid
from copy import deepcopy
from dataclasses import dataclass, field
from time import monotonic
from typing import Any

import gymnasium as gym

import chemworld  # noqa: F401
from chemworld.data.logging import observation_to_json, to_builtin
from chemworld.lab.limits import LabCapacityError
from chemworld.materials import action_material_display
from chemworld.tasks import get_task, list_tasks

_TASK_COPY: dict[str, tuple[str, str, str]] = {
    "reaction-to-assay": (
        "投料到最终检测",
        "完成投料、反应控制、终止与 final assay，学习最短的完整实验闭环。",
        "在有限预算中得到有效终点分数，同时保持轨迹合法。",
    ),
    "reaction-to-purification": (
        "反应与纯化",
        "把反应和两相分离串成一个可回放流程，观察纯度、回收率与成本的权衡。",
        "获得更纯的目标产物，同时控制转移损失。",
    ),
    "reaction-to-crystallization": (
        "反应与冷却结晶",
        "从反应生成目标物，再通过加晶种、冷却和过滤回收晶体。",
        "平衡晶体收率、纯度、粒度与过程预算。",
    ),
    "reaction-to-distillation": (
        "反应与蒸馏切割",
        "利用挥发性差异选择蒸馏条件和馏分切割。",
        "在纯度、回收率和溶剂损失之间作出可解释选择。",
    ),
    "flow-reaction-optimization": (
        "连续流反应优化",
        "通过流量、停留时间与温度控制连续流转化。",
        "兼顾转化、吞吐量和安全风险。",
    ),
    "electrochemical-conversion": (
        "电化学转化",
        "使用电位、电流和反应时间控制虚拟电化学转化。",
        "提高选择性和能量效率，同时避免过强驱动力。",
    ),
}

_EFFECTS: dict[str, tuple[str, str, str]] = {
    "add_solvent": ("累计加液", "向当前容器加入溶剂并增加体积。", "feed"),
    "add_reagent": ("累计投料", "向当前容器加入试剂，已有物料不会被替换。", "feed"),
    "add_catalyst": ("加入催化剂", "向当前容器加入催化剂。", "feed"),
    "heat": ("加热反应", "从当前组成继续演化并累计时间与热历程。", "heat"),
    "wait": ("继续反应", "当前组成继续随时间演化。", "mix"),
    "sample": ("取样", "从当前库存按比例扣除样品。", "sample"),
    "measure": ("仪器测量", "消耗样品和成本并返回公开观测。", "measure"),
    "quench": ("淬灭", "停止反应并把容器切换到淬灭状态。", "quench"),
    "terminate": ("终止实验", "标记当前过程已终止；final assay 才会完成实验。", "terminate"),
    "add_phase": ("加入液相", "向当前相账本累计加入液体。", "phase"),
    "add_extractant": ("加入萃取相", "向当前容器加入萃取相。", "phase"),
    "mix": ("混合传质", "重新分配相库存并累计混合时间。", "mix"),
    "settle": ("静置分层", "累计静置时间并更新分层状态。", "settle"),
    "separate_phase": ("选择工作相", "选择一个现有相用于后续操作。", "separate"),
    "wash": ("洗涤", "加入洗液并重新分配所选相。", "wash"),
    "dry": ("干燥", "移除水分并记录液体损失。", "dry"),
    "concentrate": ("浓缩", "减少液体库存并累计时间与损失。", "evaporate"),
    "transfer": ("转移", "转移库存并计入釜底和管线残留。", "transfer"),
    "seed_crystals": ("加入晶种", "向当前结晶实验加入晶种。", "seed"),
    "cool_crystallize": ("冷却结晶", "更新固液状态并累计冷却时间。", "crystallize"),
    "filter_crystals": ("过滤晶体", "转移固相并计入回收损失。", "filter"),
    "evaporate": ("蒸发", "移除部分液体并累计热负荷。", "evaporate"),
    "distill": ("蒸馏", "把库存拆分为馏出相与釜底相。", "distill"),
    "collect_fraction": ("收集馏分", "转移部分馏出相并计入损失。", "collect"),
    "set_flow_rate": ("设定流量", "更新流量与停留时间，本动作不处理物料。", "flow"),
    "run_flow": ("运行连续流", "按当前配置处理库存。", "flow"),
    "set_potential": ("设定电位", "更新电化学配置，本动作不发生电解。", "electro"),
    "electrolyze": ("运行电解", "按当前配置继续处理组成。", "electro"),
}

_LOCK_REASON_COPY: dict[str, str] = {
    "has_volume": "先加入溶剂或液相。",
    "has_material": "先加入至少一种反应物料。",
    "has_phase_system": "先建立包含两个液相的体系。",
    "phase_settled": "先完成混合并静置分层。",
    "measurement_sample_available": "先准备足够的可测样品。",
    "terminate_requires_material": "加入物料后才能终止本次实验。",
    "final_assay_sample_available": "需要为最终检测保留可用样品。",
    "run_flow_requires_flow_setup": "先设置连续流流量。",
    "electrolyze_requires_potential": "先设置电位和电流。",
    "seed_crystals_requires_reaction_advance": "先推进反应，再进入结晶步骤。",
    "seed_crystals_requires_current_reaction_assay": "先测量当前反应样品。",
    "cool_crystallize_requires_reaction_or_seed": "先推进反应或加入晶种。",
    "cool_crystallize_target_feed_available": "需要保留可供结晶的目标物流。",
    "filter_requires_crystallization": "先完成冷却结晶。",
    "collect_fraction_requires_distillation": "先执行蒸馏以生成馏分。",
    "flagship_crystallization_requires_isolated_crystals": "先过滤并分离晶体。",
    "flagship_electrochemistry_requires_outcome_assay": "先完成电化学结果检测。",
    "electrochemical_flagship_phase_allows_operation": "当前电化学流程阶段尚未解锁。",
    "campaign_resources_available": "当前实验预算或物料库存不足。",
}

_APPARATUS_LABELS: dict[str, str] = {
    "batch": "批式反应器",
    "separation": "液液分离系统",
    "crystallization": "冷却结晶系统",
    "distillation": "蒸馏与馏分收集",
    "flow": "连续流反应器",
    "electrochemical": "电化学反应池",
}


def _title(task_id: str) -> str:
    return task_id.replace("-", " ").title()


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


def task_catalog() -> list[dict[str, Any]]:
    """Return public task cards consumed by the browser application."""

    cards: list[dict[str, Any]] = []
    for task in list_tasks():
        title, background, goal = _TASK_COPY.get(
            task.task_id,
            (_title(task.task_id), task.description, "设计合法、可回放且资源受控的实验路径。"),
        )
        apparatus_family = _apparatus_family(task.allowed_operations)
        cards.append(
            {
                "task_id": task.task_id,
                "title": title,
                "background": background,
                "student_goal": goal,
                "description": task.description,
                "budget": task.budget,
                "episode_mode": task.episode_mode,
                "seeds": list(task.seeds),
                "success_metrics": list(task.success_metrics),
                "physics_maturity": task.kernel_maturity.lowest_level.value,
                "proxy_allowed": task.kernel_maturity.proxy_allowed,
                "allowed_operations": list(task.allowed_operations),
                "apparatus_family": apparatus_family,
                "apparatus_label": _APPARATUS_LABELS[apparatus_family],
            }
        )
    cards.sort(key=lambda item: (item["task_id"] != "reaction-to-assay", item["task_id"]))
    return cards


def _effect(operation: str) -> dict[str, str]:
    label, summary, visual = _EFFECTS.get(
        operation,
        ("状态更新", "更新当前公开实验状态。", "generic"),
    )
    return {"label": label, "summary": summary, "visual": visual}


def _affordance(entry: dict[str, Any]) -> dict[str, Any]:
    schema = dict(entry.get("schema") or entry)
    operation = str(entry.get("operation") or schema.get("operation") or "")
    invalid_reasons = list(entry.get("invalid_reasons") or [])
    return {
        "operation": operation,
        "valid": bool(entry.get("valid", True)),
        "invalid_reasons": invalid_reasons,
        "lock_reasons": [
            _LOCK_REASON_COPY.get(
                str(reason),
                "等待前序实验条件满足。"
                if not str(reason).startswith("campaign_resource:")
                else "当前实验资源不足。",
            )
            for reason in invalid_reasons
        ],
        "required_fields": list(schema.get("required_fields") or []),
        "fields": deepcopy(schema.get("fields") or []),
        "preconditions": list(schema.get("preconditions") or []),
        "effect": _effect(operation),
    }


def _state_effects(action: dict[str, Any], info: dict[str, Any]) -> dict[str, Any]:
    delta = dict(info.get("state_delta_summary") or {})
    return {
        **_effect(str(action.get("operation") or "")),
        "delta_time_s": float(delta.get("delta_time_s", 0.0)),
        "delta_cost": float(delta.get("delta_cost", info.get("cost_delta", 0.0))),
        "delta_risk": float(delta.get("delta_risk", info.get("risk_delta", 0.0))),
        "delta_temperature_K": float(delta.get("delta_temperature_K", 0.0)),
        "delta_volume_L": float(delta.get("delta_volume_L", 0.0)),
        "sample_delta_L": float(info.get("sample_delta", 0.0)),
        "transaction_status": str(info.get("transaction_status") or "unknown"),
    }


@dataclass
class LabSession:
    """One manual browser session backed by the normal public Gym environment."""

    task_id: str
    seed: int
    session_id: str = field(default_factory=lambda: uuid.uuid4().hex)

    def __post_init__(self) -> None:
        task = get_task(self.task_id)
        self._env = gym.make("ChemWorld", **task.env_kwargs(seed=self.seed))
        self._env.reset(seed=self.seed)
        self._history: list[dict[str, Any]] = []
        self._lock = threading.RLock()

    def close(self) -> None:
        with self._lock:
            self._env.close()

    def state(self) -> dict[str, Any]:
        with self._lock:
            base: Any = self._env.unwrapped
            campaign = to_builtin(base.campaign_state())
            report = to_builtin(base.observation_view("lab_report"))
            experiment_index = int(campaign.get("experiment_index", 0))
            current = [
                row
                for row in self._history
                if int(row.get("experiment_index", -1)) == experiment_index
            ]
            effects = [dict(row.get("state_effects") or {}) for row in current]
            operations = [str(row.get("action", {}).get("operation") or "") for row in current]
            task = get_task(self.task_id)
            apparatus_family = _apparatus_family(task.allowed_operations)
            all_action_entries = {
                str(item.get("operation") or ""): item
                for item in base.available_actions(include_invalid=True)
            }
            all_actions = [
                _affordance(all_action_entries[operation])
                for operation in task.allowed_operations
                if operation in all_action_entries
            ]
            return {
                "session_id": self.session_id,
                "task_id": self.task_id,
                "seed": self.seed,
                "campaign_state": campaign,
                "lab_report": report,
                "available_actions": [_affordance(item) for item in base.available_actions()],
                "all_actions": all_actions,
                "history": list(self._history),
                "public_vessel": {
                    "experiment_index": experiment_index,
                    "vessel_relation": "cumulative" if current else "fresh",
                    "operation_count": len(current),
                    "net_volume_delta_L": sum(
                        float(item.get("delta_volume_L", 0.0)) for item in effects
                    ),
                    "elapsed_time_delta_s": sum(
                        float(item.get("delta_time_s", 0.0)) for item in effects
                    ),
                    "sampled_volume_L": sum(
                        float(item.get("sample_delta_L", 0.0)) for item in effects
                    ),
                    "apparatus_family": apparatus_family,
                    "apparatus_label": _APPARATUS_LABELS[apparatus_family],
                    "phase_active": any(
                        item
                        in {
                            "add_phase",
                            "add_extractant",
                            "mix",
                            "settle",
                            "separate_phase",
                            "wash",
                        }
                        for item in operations
                    ),
                    "solid_active": any(
                        item in {"seed_crystals", "cool_crystallize", "filter_crystals"}
                        for item in operations
                    ),
                    "flow_configured": any(
                        item in {"set_flow_rate", "run_flow"} for item in operations
                    ),
                    "electrochemical_configured": any(
                        item in {"set_potential", "electrolyze"} for item in operations
                    ),
                    "distillation_active": any(
                        item in {"evaporate", "distill", "collect_fraction"}
                        for item in operations
                    ),
                    "terminated": "terminate" in operations,
                },
                "done": bool(campaign.get("done")),
            }

    def step(self, action: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            base: Any = self._env.unwrapped
            validation = dict(base.validate_action(action))
            if not validation.get("valid", False):
                available = [item["operation"] for item in base.available_actions()]
                return {
                    "accepted": False,
                    "validation": to_builtin(validation),
                    "feedback": {
                        "message": "动作未执行，实验状态和预算均未改变。",
                        "recovery_suggestion": "当前合法动作：" + "、".join(available[:8]),
                    },
                    "state": self.state(),
                }
            campaign_before = base.campaign_state()
            observation, reward, terminated, truncated, info = self._env.step(action)
            report = to_builtin(base.observation_view("lab_report"))
            campaign = to_builtin(base.campaign_state())
            canonical = dict(validation.get("canonical_action") or action)
            record = {
                "step": len(self._history) + 1,
                "experiment_index": int(campaign_before.get("experiment_index", 0)),
                "action": to_builtin(canonical),
                "action_display": action_material_display(canonical),
                "reward": float(reward),
                "leaderboard_score": to_builtin(info.get("leaderboard_score")),
                "best_score": campaign.get("best_score"),
                "visible_metrics": report.get("visible_metrics", {}),
                "constraint_flags": to_builtin(info.get("constraint_flags", {})),
                "observation": observation_to_json(observation),
                "status": report.get("status"),
                "state_effects": _state_effects(canonical, info),
                "terminated": bool(terminated),
                "truncated": bool(truncated),
            }
            self._history.append(record)
            return {
                "accepted": True,
                "validation": to_builtin(validation),
                "feedback": {
                    "message": report.get("text"),
                    "visible_metrics": report.get("visible_metrics", {}),
                    "recovery_suggestion": report.get("recovery_suggestion"),
                },
                "record": record,
                "state": self.state(),
            }


class LabSessionManager:
    """Thread-safe in-memory session registry."""

    def __init__(
        self,
        *,
        max_sessions: int | None = None,
        session_ttl_s: float | None = None,
    ) -> None:
        if max_sessions is not None and max_sessions < 1:
            raise ValueError("max_sessions must be positive")
        if session_ttl_s is not None and session_ttl_s <= 0:
            raise ValueError("session_ttl_s must be positive")
        self._max_sessions = max_sessions
        self._session_ttl_s = session_ttl_s
        self._sessions: dict[str, LabSession] = {}
        self._last_access: dict[str, float] = {}
        self._lock = threading.RLock()

    def create(self, task_id: str, seed: int | None = None) -> LabSession:
        with self._lock:
            stale = self._prune_locked(monotonic())
            for item in stale:
                item.close()
            if self._max_sessions is not None and len(self._sessions) >= self._max_sessions:
                raise LabCapacityError("public Lab session capacity is temporarily full")
            task = get_task(task_id)
            session = LabSession(task_id=task_id, seed=task.seeds[0] if seed is None else seed)
            self._sessions[session.session_id] = session
            self._last_access[session.session_id] = monotonic()
        return session

    def get(self, session_id: str) -> LabSession:
        with self._lock:
            stale = self._prune_locked(monotonic())
            session = self._sessions.get(session_id)
            if session is not None:
                self._last_access[session_id] = monotonic()
        for item in stale:
            item.close()
        if session is None:
            raise KeyError(f"unknown lab session: {session_id}")
        return session

    def _prune_locked(self, now: float) -> list[LabSession]:
        if self._session_ttl_s is None:
            return []
        stale_ids = [
            session_id
            for session_id, accessed_at in self._last_access.items()
            if now - accessed_at >= self._session_ttl_s
        ]
        stale = [self._sessions.pop(session_id) for session_id in stale_ids]
        for session_id in stale_ids:
            self._last_access.pop(session_id, None)
        return stale

    def count(self) -> int:
        """Return the number of retained in-memory sessions."""

        with self._lock:
            return len(self._sessions)

    def close_all(self) -> None:
        with self._lock:
            sessions = list(self._sessions.values())
            self._sessions.clear()
            self._last_access.clear()
        for session in sessions:
            session.close()


__all__ = ["LabSession", "LabSessionManager", "task_catalog"]
