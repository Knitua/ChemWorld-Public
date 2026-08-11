"""Leakage-resistant training reward and behavioral-completion contracts."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from typing import Any

REWARD_SCHEMA_VERSION = "chemworld-rl-training-reward-0.4"

REWARD_COMPONENTS = {
    "raw_environment_reward": 1.0,
    "valid_nonterminal_operation": -0.002,
    "invalid_precondition": -0.25,
    "transaction_rollback": -0.25,
    "newly_unlocked_operation": 0.02,
    # A small, one-shot progress signal prevents sparse-reward policies from
    # learning to repeat a legal operation forever. Requirements are derived
    # solely from the published task operation contract, never hidden world
    # state or the benchmark objective, and repeated operations earn nothing.
    "newly_satisfied_core_requirement": 0.10,
    "behavioral_core_completion": 1.0,
    "measurement": 0.0,
    "experiment_ended": 1.0,
    "quick_close_incomplete": -1.0,
    "unsafe_step": -0.10,
    "high_cost_step": -0.05,
}


def core_operation_requirements(
    allowed_operations: Iterable[str],
    *,
    task_id: str | None = None,
) -> tuple[tuple[str, ...], ...]:
    """Derive observable behavior requirements from the task operation slice.

    Each inner tuple is an alternatives group; every group must be satisfied.
    This is deliberately based on the public task contract, not hidden state.
    """

    if task_id == "reaction-to-crystallization":
        return (
            ("thermal_conversion",),
            ("reaction_assay",),
            ("seeded_crystallization",),
            ("controlled_cooling",),
            ("crystallization_assay",),
            ("crystal_isolation",),
        )
    if task_id == "electrochemical-conversion":
        return (
            ("cell_configured",),
            ("probe_regime",),
            ("electrolyte_diagnostic",),
            ("performance_diagnostic",),
            ("adapted_setpoint",),
            ("controlled_conversion",),
            ("outcome_assay",),
        )

    allowed = set(allowed_operations)
    groups: list[tuple[str, ...]] = []
    if "run_flow" in allowed:
        groups.extend((("set_flow_rate",), ("run_flow",)))
    elif "electrolyze" in allowed:
        groups.extend((("set_potential",), ("electrolyze",)))
    elif {"heat", "wait"}.intersection(allowed):
        groups.append(tuple(item for item in ("heat", "wait") if item in allowed))

    if "cool_crystallize" in allowed:
        groups.extend((("cool_crystallize",), ("filter_crystals",)))
    if "distill" in allowed:
        groups.extend((("distill",), ("collect_fraction",)))
    if "mix" in allowed:
        groups.extend((("mix",), ("settle",), ("separate_phase",)))
    return tuple(groups)


def satisfied_requirement_count(
    requirements: tuple[tuple[str, ...], ...],
    executed_operations: set[str],
) -> int:
    return sum(bool(set(group).intersection(executed_operations)) for group in requirements)


class PublicBehaviorTracker:
    """Track task behavior using only successful public operation records.

    The two flagship tasks use ordered milestones, rather than unordered
    operation presence, so an agent cannot earn completion by shuffling the
    right verbs into a physically meaningless trajectory. Other tasks retain
    the legacy public-operation set contract.
    """

    def __init__(
        self,
        allowed_operations: Iterable[str],
        *,
        task_id: str | None = None,
    ) -> None:
        self.task_id = task_id
        self.requirements = core_operation_requirements(
            allowed_operations,
            task_id=task_id,
        )
        self.reset()

    def reset(self) -> None:
        self.tokens: set[str] = set()
        self.operation_sequence: list[str] = []
        self._first_electrochemical_setpoint: tuple[float, float] | None = None

    @property
    def satisfied_count(self) -> int:
        return satisfied_requirement_count(self.requirements, self.tokens)

    @property
    def complete(self) -> bool:
        return bool(self.requirements) and self.satisfied_count == len(self.requirements)

    @property
    def satisfied(self) -> list[bool]:
        return [bool(set(group).intersection(self.tokens)) for group in self.requirements]

    def observe(self, info: Mapping[str, Any]) -> tuple[str, ...]:
        """Consume one public step-info payload and return newly met tokens."""

        flags = dict(info.get("constraint_flags", {}))
        invalid = (
            bool(flags.get("precondition_failed", False))
            or bool(flags.get("constitution_failed", False))
            or info.get("transaction_status") == "rolled_back"
        )
        operation = str(info.get("operation_type", ""))
        if invalid or not operation:
            return ()
        instrument = str(info.get("instrument") or "")
        evidence_operation = operation
        if operation == "measure":
            if instrument:
                evidence_operation = f"measure:{instrument}"
            elif bool(info.get("experiment_ended", False)):
                evidence_operation = "measure:final_assay"
        self.operation_sequence.append(evidence_operation)
        before = set(self.tokens)
        if self.task_id == "reaction-to-crystallization":
            self._observe_crystallization(operation, instrument)
        elif self.task_id == "electrochemical-conversion":
            self._observe_electrochemistry(operation, instrument, info)
        else:
            required_operations = {candidate for group in self.requirements for candidate in group}
            if operation in required_operations:
                self.tokens.add(operation)
        return tuple(sorted(self.tokens.difference(before)))

    def card(self, *, experiment_index: int) -> dict[str, Any]:
        missing = [
            list(group)
            for group, satisfied in zip(self.requirements, self.satisfied, strict=True)
            if not satisfied
        ]
        required = sorted(
            {candidate for group in self.requirements for candidate in group}
            | {"measure:final_assay"}
        )
        return {
            "experiment_index": experiment_index,
            "operation_sequence": list(self.operation_sequence),
            "behavior_tokens": sorted(self.tokens),
            "core_operation_requirements": [list(group) for group in self.requirements],
            "missing_core_requirements": missing,
            "required_operations": required,
            "missing_required_operations": sorted(
                candidate for group in missing for candidate in group
            ),
            "behavior_complete": self.complete,
            "quick_close_incomplete": not self.complete,
            "public_operation_history_only": True,
        }

    def _observe_crystallization(self, operation: str, instrument: str) -> None:
        if operation in {"heat", "wait"}:
            self.tokens.add("thermal_conversion")
        elif (
            operation == "measure"
            and instrument != "final_assay"
            and "thermal_conversion" in self.tokens
            and "controlled_cooling" not in self.tokens
        ):
            self.tokens.add("reaction_assay")
        elif operation == "seed_crystals" and "reaction_assay" in self.tokens:
            self.tokens.add("seeded_crystallization")
        elif operation == "cool_crystallize" and "seeded_crystallization" in self.tokens:
            self.tokens.add("controlled_cooling")
        elif (
            operation == "measure"
            and instrument != "final_assay"
            and "controlled_cooling" in self.tokens
        ):
            self.tokens.add("crystallization_assay")
        elif operation == "filter_crystals" and "crystallization_assay" in self.tokens:
            self.tokens.add("crystal_isolation")

    def _observe_electrochemistry(
        self,
        operation: str,
        instrument: str,
        info: Mapping[str, Any],
    ) -> None:
        summary = dict(info.get("state_delta_summary", {}))
        if operation == "set_potential":
            setpoint = (
                float(summary.get("configured_potential_V", 0.0)),
                float(summary.get("configured_current_mA", 0.0)),
            )
            if self._first_electrochemical_setpoint is None:
                self._first_electrochemical_setpoint = setpoint
                self.tokens.add("cell_configured")
            elif {
                "electrolyte_diagnostic",
                "performance_diagnostic",
            }.issubset(self.tokens):
                first_potential, first_current = self._first_electrochemical_setpoint
                if (
                    abs(setpoint[0] - first_potential) >= 0.02
                    or abs(setpoint[1] - first_current) >= 1.0
                ):
                    self.tokens.add("adapted_setpoint")
        elif operation == "electrolyze":
            if "cell_configured" in self.tokens and "probe_regime" not in self.tokens:
                self.tokens.add("probe_regime")
            elif "adapted_setpoint" in self.tokens:
                self.tokens.add("controlled_conversion")
        elif operation == "measure" and "probe_regime" in self.tokens:
            if instrument == "ph_meter" and "controlled_conversion" not in self.tokens:
                self.tokens.add("electrolyte_diagnostic")
            elif instrument == "uvvis":
                if "controlled_conversion" in self.tokens:
                    self.tokens.add("outcome_assay")
                else:
                    self.tokens.add("performance_diagnostic")


def reward_contract(
    allowed_operations: Iterable[str],
    *,
    task_id: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": REWARD_SCHEMA_VERSION,
        "public_signals_only": True,
        "benchmark_evaluation_uses_shaped_reward": False,
        "components": dict(REWARD_COMPONENTS),
        "behavioral_completion": {
            "requirements": [
                list(group)
                for group in core_operation_requirements(
                    allowed_operations,
                    task_id=task_id,
                )
            ],
            "all_requirements_must_be_satisfied": True,
            "experiment_end_without_core_behavior": "quick_close_incomplete",
            "ordered_flagship_milestones": task_id
            in {"reaction-to-crystallization", "electrochemical-conversion"},
        },
        "leakage_controls": {
            "terminal_bonus": True,
            "terminal_bonus_requires_public_behavioral_completion": True,
            "measurement_bonus": False,
            "core_progress_uses_public_operation_history_only": True,
            "repeated_core_operation_bonus": False,
            "raw_environment_reward_semantics": "fresh_measurement_score_delta",
            "non_measurement_raw_reward_zero": True,
            "cached_observation_reward": False,
            "raw_benchmark_reward_preserved": True,
        },
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    payload["contract_hash"] = hashlib.sha256(encoded).hexdigest()
    return payload


__all__ = [
    "REWARD_COMPONENTS",
    "REWARD_SCHEMA_VERSION",
    "PublicBehaviorTracker",
    "core_operation_requirements",
    "reward_contract",
    "satisfied_requirement_count",
]
