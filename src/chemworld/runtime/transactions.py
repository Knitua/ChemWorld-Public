"""Transactional state updates for ChemWorld runtime v2."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

from chemworld.foundation import PhysicalConstitution, WorldState


@dataclass(frozen=True)
class WorldEvent:
    event_type: str
    operation_type: str
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type,
            "operation_type": self.operation_type,
            "payload": dict(self.payload),
        }


@dataclass(frozen=True)
class StatePatch:
    patch_type: str
    affected_ledgers: tuple[str, ...]
    state: WorldState | None = None
    summary: dict[str, Any] = field(default_factory=dict)

    def apply(self, state: WorldState) -> WorldState:
        if self.patch_type in {"replace_state", "rollback_penalty"} and self.state is not None:
            return self.state
        return state

    def to_dict(self) -> dict[str, Any]:
        return {
            "patch_type": self.patch_type,
            "affected_ledgers": list(self.affected_ledgers),
            "summary": dict(self.summary),
        }


@dataclass(frozen=True)
class TransactionResult:
    state: WorldState
    events: tuple[WorldEvent, ...]
    patches: tuple[StatePatch, ...]
    transaction_status: str
    rollback_reason: str | None
    constitution_checks: tuple[dict[str, object], ...]

    def to_info(self) -> dict[str, Any]:
        return {
            "world_events": [event.to_dict() for event in self.events],
            "state_patches_summary": [patch.to_dict() for patch in self.patches],
            "transaction_status": self.transaction_status,
            "rollback_reason": self.rollback_reason,
        }


class TransactionManager:
    """Apply patches atomically and roll back failed constitution checks."""

    def __init__(self, constitution: PhysicalConstitution) -> None:
        self.constitution = constitution

    def commit(
        self,
        *,
        state: WorldState,
        operation_type: str,
        events: tuple[WorldEvent, ...],
        patches: tuple[StatePatch, ...],
    ) -> TransactionResult:
        candidate = state
        for patch in patches:
            candidate = patch.apply(candidate)
        report = self.constitution.check_state(candidate)
        checks = tuple(check.to_dict() for check in report.checks)
        if report.passed:
            return TransactionResult(
                state=candidate,
                events=events,
                patches=patches,
                transaction_status="committed",
                rollback_reason=None,
                constitution_checks=checks,
            )
        penalty_state = self._penalize_rollback(state)
        failed_checks = [check["name"] for check in checks if not check["passed"]]
        rollback_event = WorldEvent(
            "transaction_rollback",
            operation_type,
            {"failed_checks": failed_checks},
        )
        rollback_patch = StatePatch(
            patch_type="rollback_penalty",
            affected_ledgers=("process",),
            state=penalty_state,
            summary={
                "delta_cost": penalty_state.ledger.cost - state.ledger.cost,
                "delta_risk": penalty_state.ledger.risk - state.ledger.risk,
                "delta_sample_consumed_L": (
                    penalty_state.ledger.sample_consumed_L
                    - state.ledger.sample_consumed_L
                ),
                "failed_checks": failed_checks,
            },
        )
        return TransactionResult(
            state=penalty_state,
            events=(*events, rollback_event),
            patches=(*patches, rollback_patch),
            transaction_status="rolled_back",
            rollback_reason="constitution_failed",
            constitution_checks=checks,
        )

    def rollback(
        self,
        *,
        state: WorldState,
        operation_type: str,
        rollback_reason: str,
        failed_preconditions: tuple[str, ...] = (),
        failed_checks: tuple[str, ...] = (),
        events: tuple[WorldEvent, ...] = (),
    ) -> TransactionResult:
        """Rollback an action before candidate-state mutation is committed."""

        penalty_state = self._penalize_rollback(state)
        payload: dict[str, Any] = {"rollback_reason": rollback_reason}
        if failed_preconditions:
            payload["failed_preconditions"] = list(failed_preconditions)
        if failed_checks:
            payload["failed_checks"] = list(failed_checks)
        rollback_event = WorldEvent("transaction_rollback", operation_type, payload)
        rollback_patch = StatePatch(
            patch_type="rollback_penalty",
            affected_ledgers=("process",),
            state=penalty_state,
            summary={
                "delta_cost": penalty_state.ledger.cost - state.ledger.cost,
                "delta_risk": penalty_state.ledger.risk - state.ledger.risk,
                "delta_sample_consumed_L": (
                    penalty_state.ledger.sample_consumed_L
                    - state.ledger.sample_consumed_L
                ),
                "failed_preconditions": list(failed_preconditions),
                "failed_checks": list(failed_checks),
            },
        )
        checks = tuple(check.to_dict() for check in self.constitution.check_state(state).checks)
        return TransactionResult(
            state=penalty_state,
            events=(*events, rollback_event),
            patches=(rollback_patch,),
            transaction_status="rolled_back",
            rollback_reason=rollback_reason,
            constitution_checks=checks,
        )

    @staticmethod
    def _penalize_rollback(state: WorldState) -> WorldState:
        ledger = state.ledger.with_updates(
            cost=state.ledger.cost + 0.03,
            risk=min(1.0, state.ledger.risk + 0.08),
        )
        process = None
        if state.process is not None:
            process = replace(
                state.process,
                cost=ledger.cost,
                risk=ledger.risk,
            )
        return state.replace(ledger=ledger, process=process)


__all__ = ["StatePatch", "TransactionManager", "TransactionResult", "WorldEvent"]
