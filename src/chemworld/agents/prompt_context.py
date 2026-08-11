"""Bounded, decision-first prompt representation for live benchmark agents."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from chemworld.data.logging import to_builtin

PROMPT_CONTEXT_VERSION = "chemworld-compact-decision-context-0.3"
DEFAULT_PROMPT_TOKEN_ESTIMATE_CAP = 1500
PROMPT_TOKEN_ESTIMATE_SAFETY_MARGIN = 50

_TASK_KEYS = (
    "task_id",
    "task_goal",
    "objective",
    "description",
    "budget",
    "episode_mode",
    "safety_limit",
    "success_metrics",
    "termination_policy",
    "electrochemical_workflow_mode",
    "scoring_contract_id",
)
_LIFECYCLE_KEYS = (
    "fresh_experiment_precondition",
    "terminate_effect",
    "final_assay_precondition",
    "final_assay_effect",
)
_STATE_KEYS = (
    "experiment_index",
    "diagnostic_actions_used_current_experiment",
    "diagnostic_per_experiment_action_limit",
    "remaining_budget",
    "remaining_experiments",
    "remaining_operations",
    "cost",
    "risk",
    "score",
    "leaderboard_score",
    "temperature_K",
    "pressure_Pa",
    "elapsed_time_s",
    "solvent",
    "electrolyte_profile",
    "catalyst",
    "catalyst_amount_mol",
)
_PEAK_FIELDS = (
    "spectrum_id",
    "instrument",
    "kind",
    "assignment",
    "center",
    "retention_time",
    "retention_time_min",
    "chemical_shift",
    "wavelength",
    "wavenumber",
    "area",
    "height",
    "width",
    "fraction",
    "concentration",
    "concentration_mol_L",
)
_SKIPPED_ARRAY_KEYS = frozenset(
    {
        "axis",
        "axes",
        "intensity",
        "intensities",
        "replicate_signals",
        "signal",
        "signals",
        "values",
    }
)
_PURE_SPECTRAL_PACKET_KINDS = frozenset(
    {
        "gc_chromatogram",
        "hplc_chromatogram",
        "ir_spectrum",
        "nmr_1h_spectrum",
        "uvvis_spectrum",
    }
)


class PromptBudgetExceededError(ValueError):
    """The public decision state cannot fit without dropping required fields."""


@dataclass(frozen=True)
class PromptPacket:
    payload: dict[str, Any]
    text: str
    estimated_tokens: int
    max_estimated_tokens: int
    reduction_steps: tuple[str, ...]


def build_decision_prompt(
    *,
    task_contract: Mapping[str, Any],
    decision_context: Mapping[str, Any],
    tool_json: Mapping[str, Any],
    experiment_memory: Sequence[Mapping[str, Any]],
    recent_decisions: Sequence[Mapping[str, Any]],
    max_estimated_tokens: int = DEFAULT_PROMPT_TOKEN_ESTIMATE_CAP,
) -> PromptPacket:
    """Return one compact prompt without raw arrays or duplicated public views."""

    if max_estimated_tokens < 500:
        raise ValueError("prompt token estimate cap must be at least 500")
    state_raw = decision_context.get("campaign_state", {})
    state = state_raw if isinstance(state_raw, Mapping) else {}
    actions = tool_json.get("available_actions", [])
    g2_campaign = (
        task_contract.get("electrochemical_workflow_mode")
        == "autonomous_open_v1"
    )
    payload: dict[str, Any] = {
        "representation_version": PROMPT_CONTEXT_VERSION,
        "instruction": (
            "Choose a legal operation from the public state. Declare "
            "which outcome would support or weaken the diagnostic target. Request a "
            "historical spectrum only when its detail can change the decision. The "
            "action must be a flat JSON object: every required field is a direct "
            "sibling of operation; never nest values under parameters. The harness "
            "does not repair, terminate, or assay on your behalf."
        ),
        "task": _compact_task_contract(task_contract),
        "decision_state": {
            "step": decision_context.get("step"),
            "stage": decision_context.get("decision_stage"),
            "remaining_operations": decision_context.get(
                "remaining_operations",
                state.get("remaining_budget"),
            ),
            "current_experiment": _pick_compact(state, _STATE_KEYS),
            **(
                {
                    "campaign_resources": _compact_campaign_resources(
                        state.get("campaign_resources")
                    )
                }
                if g2_campaign
                else {}
            ),
            "lifecycle": _compact_lifecycle_state(
                decision_context,
                state,
            ),
            "latest_metrics": _compact_scalar_mapping(
                decision_context.get("visible_metrics", {})
            ),
            "latest_measurement": summarize_measurement(
                decision_context.get("latest_spectra", {})
            ),
            "requested_historical_measurement": summarize_measurement(
                decision_context.get("requested_historical_spectrum", {})
            ),
            "active_constraint_flags": _active_flags(
                decision_context.get("constraint_flags", {})
            ),
            "uncertainty": _compact_scalar_mapping(
                decision_context.get("uncertainty", {})
            ),
            "observation_provenance": _pick_compact(
                _mapping(decision_context.get("observation_provenance")),
                (
                    "current_event_type",
                    "current_spectral_packet",
                    "latest_cataloged_spectrum_id",
                    "latest_spectrum_measurement_step",
                    "operations_since_latest_spectrum",
                ),
            ),
        },
        "experiment_memory": compact_experiment_memory(experiment_memory),
        "recent_decisions": [
            compact_decision(item) for item in recent_decisions[-2:]
        ],
        "legal_actions": [
            compact_action(item)
            for item in actions
            if (
                isinstance(item, Mapping)
                and item.get("operation")
                and item.get("valid") is not False
            )
        ]
        if isinstance(actions, list)
        else [],
        "on_demand_detail": {
            "historical_spectrum": (
                "set request_historical_spectrum_id to a supplied public spectrum_id"
            ),
            "historical_spectrum_catalog": _compact_spectrum_catalog(
                decision_context.get("historical_spectrum_catalog", ())
            ),
        },
        "required_json_shape": {
            "action": {
                "operation": "one legal operation",
                "<required field>": "value as a direct sibling of operation",
            },
            "expected_effect": "one concise testable expectation",
            "diagnostic_target": "candidate relation or exploitation objective",
            "expected_information_gain": "unitless forecast in [0,1]",
            "belief_update_rule": {
                "if_supported": "belief or next-step change",
                "if_not_supported": "belief or next-step change",
            },
            "uncertainty": "number in [0,1]",
            "request_historical_spectrum_id": (
                "public spectrum_id needed next, or null"
            ),
        },
    }
    return serialize_prompt_payload(payload, max_estimated_tokens=max_estimated_tokens)


def serialize_prompt_payload(
    payload: Mapping[str, Any],
    *,
    max_estimated_tokens: int,
) -> PromptPacket:
    """Serialize under a hard cap; never silently remove required action fields."""

    mutable = to_builtin(dict(payload))
    reduction_steps: list[str] = []
    text = _canonical_json(mutable)
    estimate = estimate_prompt_tokens(text)
    reduction_target = max(
        500,
        max_estimated_tokens - PROMPT_TOKEN_ESTIMATE_SAFETY_MARGIN,
    )
    if estimate > reduction_target:
        reduction_steps.append("trim_recent_uncertainty_and_peak_detail")
        mutable["recent_decisions"] = list(mutable.get("recent_decisions", []))[-1:]
        state = mutable.get("decision_state")
        if isinstance(state, dict):
            state["uncertainty"] = {}
            for measurement_key in (
                "latest_measurement",
                "requested_historical_measurement",
            ):
                measurement = state.get(measurement_key)
                if isinstance(measurement, dict) and isinstance(
                    measurement.get("peaks"), list
                ):
                    measurement["peaks"] = measurement["peaks"][:4]
                    measurement["peak_summary_truncated"] = True
        manifest = mutable.get("context_manifest")
        if isinstance(manifest, dict):
            manifest["fixed_budget_reduction_applied"] = True
        text = _canonical_json(mutable)
        estimate = estimate_prompt_tokens(text)
    if estimate > reduction_target:
        reduction_steps.append("trim_actions_catalog_and_peak_detail")
        recent = mutable.get("recent_decisions")
        if isinstance(recent, list):
            for item in recent:
                if isinstance(item, dict):
                    item.pop("action", None)
        state = mutable.get("decision_state")
        if isinstance(state, dict):
            for measurement_key in (
                "latest_measurement",
                "requested_historical_measurement",
            ):
                measurement = state.get(measurement_key)
                if isinstance(measurement, dict) and isinstance(
                    measurement.get("peaks"), list
                ):
                    measurement["peaks"] = measurement["peaks"][:2]
        on_demand = mutable.get("on_demand_detail")
        if isinstance(on_demand, dict):
            catalog = on_demand.get("historical_spectrum_catalog")
            if isinstance(catalog, list):
                on_demand["historical_spectrum_catalog"] = catalog[-2:]
        text = _canonical_json(mutable)
        estimate = estimate_prompt_tokens(text)
    if estimate > reduction_target:
        reduction_steps.append("project_recent_memory_and_measurements")
        recent = mutable.get("recent_decisions")
        if isinstance(recent, list):
            mutable["recent_decisions"] = [
                _minimal_recent_decision(item)
                for item in recent[-1:]
                if isinstance(item, Mapping)
            ]
        state = mutable.get("decision_state")
        if isinstance(state, dict):
            latest_metrics = state.get("latest_metrics")
            latest_measurement = state.get("latest_measurement")
            if (
                isinstance(latest_metrics, Mapping)
                and latest_metrics
                and isinstance(latest_measurement, dict)
            ):
                latest_measurement.pop("processed_estimate", None)
            for measurement_key in (
                "latest_measurement",
                "requested_historical_measurement",
            ):
                measurement = state.get(measurement_key)
                if isinstance(measurement, dict) and isinstance(
                    measurement.get("peaks"), list
                ):
                    measurement["peaks"] = measurement["peaks"][:3]
        memory = mutable.get("experiment_memory")
        if isinstance(memory, dict) and isinstance(memory.get("recent"), list):
            memory["recent"] = memory["recent"][-1:]
        on_demand = mutable.get("on_demand_detail")
        if isinstance(on_demand, dict):
            catalog = on_demand.get("historical_spectrum_catalog")
            if isinstance(catalog, list):
                on_demand["historical_spectrum_catalog"] = catalog[-4:]
        text = _canonical_json(mutable)
        estimate = estimate_prompt_tokens(text)
    if estimate > reduction_target:
        reduction_steps.append("trim_on_demand_and_provenance")
        on_demand = mutable.get("on_demand_detail")
        if isinstance(on_demand, dict):
            on_demand.pop("historical_spectrum", None)
        state = mutable.get("decision_state")
        if isinstance(state, dict):
            provenance = state.get("observation_provenance")
            if isinstance(provenance, dict):
                provenance.pop("current_event_type", None)
                provenance.pop("current_spectral_packet", None)
        text = _canonical_json(mutable)
        estimate = estimate_prompt_tokens(text)
    if estimate > reduction_target:
        reduction_steps.append("project_prior_scientific_state")
        prior_state = mutable.get("prior_scientific_state")
        if isinstance(prior_state, dict):
            mutable["prior_scientific_state"] = _project_prior_scientific_state(
                prior_state
            )
        text = _canonical_json(mutable)
        estimate = estimate_prompt_tokens(text)
    if estimate > reduction_target:
        reduction_steps.append("drop_optional_campaign_ledger_detail")
        state = mutable.get("decision_state")
        if isinstance(state, dict):
            state.pop("campaign_resources", None)
        text = _canonical_json(mutable)
        estimate = estimate_prompt_tokens(text)
    if estimate > reduction_target:
        reduction_steps.append("drop_optional_material_contract_detail")
        task = mutable.get("task")
        if isinstance(task, dict):
            task.pop("material_catalog", None)
            task.pop("material_information", None)
            task.pop("scoring_contract", None)
        text = _canonical_json(mutable)
        estimate = estimate_prompt_tokens(text)
    if estimate > max_estimated_tokens:
        raise PromptBudgetExceededError(
            f"compact prompt estimate {estimate} exceeds cap "
            f"{max_estimated_tokens}; revise the public representation explicitly"
        )
    return PromptPacket(
        payload=mutable,
        text=text,
        estimated_tokens=estimate,
        max_estimated_tokens=max_estimated_tokens,
        reduction_steps=tuple(reduction_steps),
    )


def estimate_prompt_tokens(text: str) -> int:
    """Conservative tokenizer-independent estimate for mixed-language JSON."""

    return math.ceil(len(text.encode("utf-8")) / 4)


def estimate_prompt_segments(payload: Mapping[str, Any]) -> dict[str, int]:
    """Audit shared public context separately from persistent Agent memory."""

    memory_keys = {
        "experiment_memory",
        "recent_decisions",
        "prior_scientific_state",
    }
    environment_keys = {
        "task",
        "decision_state",
        "legal_actions",
        "on_demand_detail",
    }
    environment = {
        str(key): to_builtin(value)
        for key, value in payload.items()
        if key in environment_keys
    }
    method_contract = {
        str(key): to_builtin(value)
        for key, value in payload.items()
        if key not in memory_keys and key not in environment_keys
    }
    memory = {
        str(key): to_builtin(value)
        for key, value in payload.items()
        if key in memory_keys
    }
    return {
        "environment_view_estimated_tokens": estimate_prompt_tokens(
            _canonical_json(environment)
        ),
        "method_contract_estimated_tokens": estimate_prompt_tokens(
            _canonical_json(method_contract)
        ),
        "agent_memory_estimated_tokens": (
            estimate_prompt_tokens(_canonical_json(memory)) if memory else 0
        ),
        "total_estimated_tokens": estimate_prompt_tokens(
            _canonical_json(to_builtin(dict(payload)))
        ),
    }


def summarize_measurement(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or not value:
        return {"available": False}
    if value.get("has_spectral_packet") is False:
        return {"available": False}
    masked = value.get("spectrum_condition") == "masked"
    summary: dict[str, Any] = {
        "available": False
        if masked
        else bool(value.get("has_spectral_packet", True)),
    }
    for key in (
        "spectrum_id",
        "instrument",
        "kind",
        "measurement_step",
        "spectrum_condition",
    ):
        if _is_compact_value(value.get(key)):
            summary[key] = to_builtin(value[key])
    peaks: list[dict[str, Any]] = []
    _collect_peaks(value, peaks)
    if peaks:
        unique_peaks = _deduplicate_rows(peaks)
        summary["peaks"] = unique_peaks[:8]
        summary["peak_count_supplied"] = min(len(unique_peaks), 8)
    processed = value.get("processed_estimate")
    if isinstance(processed, Mapping):
        summary["processed_estimate"] = _compact_scalar_mapping(
            processed,
            limit=16,
        )
    raw = value.get("raw_signal")
    if isinstance(raw, Mapping):
        for key in ("spectrum_id", "instrument", "kind"):
            if key not in summary and _is_compact_value(raw.get(key)):
                summary[key] = to_builtin(raw[key])
        if raw.get("kind") not in _PURE_SPECTRAL_PACKET_KINDS:
            non_spectral = _compact_nested_scalars(raw)
            if non_spectral:
                summary["non_spectral_estimate"] = non_spectral
    return summary


def compact_experiment_memory(
    memory: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    if not memory:
        return {"historical_best": None, "recent": []}
    scored = [
        item
        for item in memory
        if _numeric_score(item) is not None
    ]
    best = (
        max(scored, key=lambda item: float(_numeric_score(item) or 0.0))
        if scored
        else memory[-1]
    )
    compact_best = _compact_experiment(best)
    compact_recent = [_compact_experiment(item) for item in memory[-2:]]
    compact_recent = [
        item
        for item in compact_recent
        if _canonical_json(item) != _canonical_json(compact_best)
    ]
    return {
        "historical_best": compact_best,
        "recent": compact_recent,
    }


def compact_decision(item: Mapping[str, Any]) -> dict[str, Any]:
    action = item.get("action")
    compact = {
        "action": to_builtin(dict(action)) if isinstance(action, Mapping) else {},
    }
    compact.update(
        _pick_compact(
            item,
            (
                "expected_effect",
                "diagnostic_target",
                "observed_effect",
                "uncertainty",
                "request_historical_spectrum_id",
                "status",
                "mechanism_distribution",
                "declared_information_value",
            ),
        )
    )
    mechanism_distribution = item.get("mechanism_distribution")
    if isinstance(mechanism_distribution, Mapping):
        compact["mechanism_distribution"] = _compact_scalar_mapping(
            mechanism_distribution,
            limit=8,
        )
    return compact


def _minimal_recent_decision(item: Mapping[str, Any]) -> dict[str, Any]:
    """Keep the prior action and belief while dropping repeated prose."""

    compact: dict[str, Any] = {}
    action = item.get("action")
    if isinstance(action, Mapping):
        compact["action"] = to_builtin(dict(action))
    mechanism_distribution = item.get("mechanism_distribution")
    if isinstance(mechanism_distribution, Mapping):
        compact["mechanism_distribution"] = _compact_scalar_mapping(
            mechanism_distribution,
            limit=8,
        )
    compact.update(
        _pick_compact(
            item,
            (
                "declared_information_value",
                "uncertainty",
            ),
        )
    )
    return compact


def _project_prior_scientific_state(
    state: Mapping[str, Any],
) -> dict[str, Any]:
    """Project audited state to the bounded fields needed for the next choice."""

    projected: dict[str, Any] = {}
    distribution = state.get("mechanism_distribution")
    if isinstance(distribution, Mapping):
        projected["mechanism_distribution"] = _compact_scalar_mapping(
            distribution,
            limit=8,
        )
    plan = state.get("campaign_plan")
    if isinstance(plan, list):
        for item in plan:
            if not isinstance(item, Mapping):
                continue
            step = item.get("step")
            if _is_compact_value(step):
                projected["current_plan_step"] = to_builtin(step)
                break
    evidence = state.get("evidence_ledger")
    evidence_supplied = False
    if isinstance(evidence, list):
        for item in reversed(evidence):
            if not isinstance(item, Mapping):
                continue
            compact_evidence = _pick_compact(
                item,
                ("supports", "contradicts"),
            )
            if compact_evidence:
                projected["latest_evidence"] = compact_evidence
                evidence_supplied = True
                break
    if not evidence_supplied:
        projected.update(_pick_compact(state, ("replan_trigger",)))
    projected.update(_pick_compact(state, ("uncertainty",)))
    return projected


def compact_action(item: Mapping[str, Any]) -> dict[str, Any]:
    compact: dict[str, Any] = {"operation": item.get("operation")}
    if item.get("valid") is False:
        compact["currently_valid"] = False
        reasons = item.get("invalid_reasons")
        if isinstance(reasons, list):
            compact["invalid_reasons"] = [
                str(reason) for reason in reasons[:4]
            ]
    schema = item.get("schema")
    if not isinstance(schema, Mapping):
        return compact
    required_raw = schema.get("required_fields", [])
    required = set(required_raw) if isinstance(required_raw, list) else set()
    fields = schema.get("fields")
    if isinstance(fields, list):
        for field in fields:
            if not isinstance(field, Mapping):
                continue
            name = field.get("field", field.get("name"))
            if not isinstance(name, str) or not name:
                continue
            parameter: dict[str, Any] = {}
            if name not in required:
                parameter["optional"] = True
            parameter.update(
                _pick_compact(
                    field,
                    (
                        "minimum",
                        "maximum",
                        "min",
                        "max",
                        "unit",
                        "choices",
                        "default",
                    ),
                )
            )
            bounds = field.get("bounds")
            if isinstance(bounds, Mapping):
                low = bounds.get("low")
                high = bounds.get("high")
                if _is_compact_value(low) and _is_compact_value(high):
                    parameter["range"] = [to_builtin(low), to_builtin(high)]
            recommended = field.get("recommended_range")
            if isinstance(recommended, Mapping):
                low = recommended.get("low")
                high = recommended.get("high")
                range_value = parameter.get("range")
                recommended_value = [to_builtin(low), to_builtin(high)]
                if (
                    _is_compact_value(low)
                    and _is_compact_value(high)
                    and recommended_value != range_value
                ):
                    parameter["recommended_range"] = [
                        to_builtin(low),
                        to_builtin(high),
                    ]
            compact[name] = parameter
    return compact


def _compact_task_contract(task_contract: Mapping[str, Any]) -> dict[str, Any]:
    compact = _pick_compact(task_contract, _TASK_KEYS)
    if task_contract.get("electrochemical_workflow_mode") == "autonomous_open_v1":
        for key in (
            "material_information",
            "material_catalog",
            "scoring_contract",
        ):
            value = task_contract.get(key)
            if isinstance(value, Mapping):
                compact[key] = to_builtin(dict(value))
    method_budget = task_contract.get("method_budget_contract")
    if isinstance(method_budget, Mapping):
        compact["method_budget_contract"] = _compact_scalar_mapping(
            method_budget,
            limit=8,
        )
    lifecycle = task_contract.get("experiment_lifecycle")
    if isinstance(lifecycle, Mapping):
        compact["experiment_lifecycle"] = _pick_compact(
            lifecycle,
            _LIFECYCLE_KEYS,
        )
    return compact


def _compact_campaign_resources(value: Any) -> dict[str, Any]:
    """Expose the public multi-ledger state without copying its event history."""

    if not isinstance(value, Mapping):
        return {}
    state = value.get("state")
    state_mapping = state if isinstance(state, Mapping) else {}
    remaining = state_mapping.get("remaining")
    remaining_mapping = remaining if isinstance(remaining, Mapping) else {}
    lifecycle = value.get("lifecycle_reserve")
    lifecycle_mapping = lifecycle if isinstance(lifecycle, Mapping) else {}
    card = value.get("card")
    card_mapping = card if isinstance(card, Mapping) else {}
    hard_limits = card_mapping.get("hard_limits")
    hard_limit_mapping = hard_limits if isinstance(hard_limits, Mapping) else {}
    current = value.get("current_experiment")
    current_mapping = current if isinstance(current, Mapping) else {}
    latest = value.get("latest_receipt")
    latest_mapping = latest if isinstance(latest, Mapping) else {}

    result = {
        "ledger_sha256": value.get("ledger_sha256"),
        "campaign_terminal": value.get("campaign_terminal"),
        "campaign_terminal_reason": value.get("campaign_terminal_reason"),
        "card": {
            "card_id": card_mapping.get("card_id"),
            "hard_limits": {
                **_pick_compact(
                    hard_limit_mapping,
                    (
                        "operation_attempts",
                        "vessel_starts",
                        "final_assays",
                        "nonfinal_instrument_uses",
                    ),
                ),
                "stocks": _compact_scalar_mapping(
                    hard_limit_mapping.get("stocks", {}),
                    limit=16,
                ),
                "per_instrument": _compact_scalar_mapping(
                    hard_limit_mapping.get("per_instrument", {}),
                    limit=16,
                ),
            },
        },
        "current_experiment": _pick_compact(
            current_mapping,
            ("experiment_index", "vessel_started"),
        ),
        "used": {
            **_pick_compact(
                state_mapping,
                (
                    "operation_attempts",
                    "vessel_starts",
                    "final_assays",
                    "closed_batches",
                    "discarded_batches",
                    "nonfinal_instrument_uses",
                ),
            ),
            "stocks": _compact_scalar_mapping(
                state_mapping.get("stocks_used", {}),
                limit=16,
            ),
            "instrument_uses": _compact_scalar_mapping(
                state_mapping.get("instrument_uses", {}),
                limit=16,
            ),
        },
        "remaining": {
            **_pick_compact(
                remaining_mapping,
                (
                    "operation_attempts",
                    "vessel_starts",
                    "final_assays",
                    "nonfinal_instrument_uses",
                ),
            ),
            "stocks": _compact_scalar_mapping(
                remaining_mapping.get("stocks", {}),
                limit=16,
            ),
            "per_instrument": _compact_scalar_mapping(
                remaining_mapping.get("per_instrument", {}),
                limit=16,
            ),
        },
        "lifecycle_reserve": {
            **_pick_compact(
                lifecycle_mapping,
                (
                    "policy",
                    "remaining_operation_attempts",
                    "future_unstarted_batches",
                    "discretionary_attempts_before_final_assay_floor",
                ),
            ),
            "current_batch": _compact_scalar_mapping(
                lifecycle_mapping.get("current_batch", {}),
                limit=8,
            ),
            "minimum_fresh_batch_operations": _compact_scalar_mapping(
                lifecycle_mapping.get("minimum_fresh_batch_operations", {}),
                limit=8,
            ),
            "minimum_future_batch_operation_reserve": _compact_scalar_mapping(
                lifecycle_mapping.get("minimum_future_batch_operation_reserve", {}),
                limit=8,
            ),
            "recommended_remaining_attempt_floor": _compact_scalar_mapping(
                lifecycle_mapping.get("recommended_remaining_attempt_floor", {}),
                limit=8,
            ),
        },
        "latest_receipt": _pick_compact(
            latest_mapping,
            (
                "event_id",
                "accepted",
                "committed",
                "rejection_reason",
            ),
        ),
    }
    return {
        str(key): item
        for key, item in result.items()
        if item not in (None, "", {}, [])
    }


def _compact_lifecycle_state(
    decision_context: Mapping[str, Any],
    campaign_state: Mapping[str, Any],
) -> dict[str, Any]:
    """Expose public lifecycle counters without selecting a scientific action."""

    raw_count = campaign_state.get(
        "diagnostic_actions_used_current_experiment"
    )
    raw_limit = campaign_state.get("diagnostic_per_experiment_action_limit")
    count = (
        int(raw_count)
        if isinstance(raw_count, int) and not isinstance(raw_count, bool)
        else None
    )
    limit = (
        int(raw_limit)
        if isinstance(raw_limit, int) and not isinstance(raw_limit, bool)
        else None
    )
    stage = str(decision_context.get("decision_stage") or "")
    terminated = stage == "experiment_closeout"
    available_raw = decision_context.get("available_operations", ())
    available = (
        {str(item) for item in available_raw}
        if isinstance(available_raw, list | tuple)
        else set()
    )
    final_assay_available = terminated and "measure" in available
    reserved = 2
    ordinary_remaining = (
        max(limit - count - reserved, 0)
        if count is not None and limit is not None
        else None
    )
    if terminated:
        closeout_status = "terminated_awaiting_final_assay"
    elif ordinary_remaining == 0:
        closeout_status = "reserved_closeout_window"
    else:
        closeout_status = "not_started"
    return {
        key: value
        for key, value in {
            "experiment_action_count": count,
            "experiment_action_limit": limit,
            "ordinary_action_slots_remaining": ordinary_remaining,
            "reserved_closeout_slots": reserved,
            "experiment_terminated": terminated,
            "final_assay_available": final_assay_available,
            "closeout_status": closeout_status,
        }.items()
        if value is not None
    }


def _compact_spectrum_catalog(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list | tuple):
        return []
    result: list[dict[str, Any]] = []
    for item in value[-8:]:
        if not isinstance(item, Mapping):
            continue
        compact = _pick_compact(
            item,
            (
                "spectrum_id",
                "instrument",
                "kind",
                "measurement_step",
                "experiment_index",
            ),
        )
        if compact.get("spectrum_id"):
            result.append(compact)
    return result


def _compact_experiment(item: Mapping[str, Any]) -> dict[str, Any]:
    compact = _pick_compact(
        item,
        (
            "experiment_index",
            "score",
            "leaderboard_score",
            "yield",
            "selectivity",
            "cost",
            "risk",
            "outcome",
        ),
    )
    visible = item.get("visible_metrics")
    if isinstance(visible, Mapping):
        compact["visible_metrics"] = _compact_scalar_mapping(visible, limit=12)
    flags = item.get("constraint_flags")
    if isinstance(flags, Mapping):
        compact["active_constraint_flags"] = _active_flags(flags)
    operations = item.get("operation_sequence", item.get("actions", []))
    if isinstance(operations, list):
        compact["operations"] = [
            str(operation.get("operation"))
            for operation in operations[-8:]
            if isinstance(operation, Mapping) and operation.get("operation")
        ]
    return compact


def _numeric_score(item: Mapping[str, Any]) -> float | None:
    for key in ("score", "leaderboard_score"):
        value = item.get(key)
        if isinstance(value, int | float) and not isinstance(value, bool):
            return float(value)
    return None


def _collect_peaks(value: Any, output: list[dict[str, Any]]) -> None:
    if len(output) >= 16:
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            if str(key).lower() in _SKIPPED_ARRAY_KEYS:
                continue
            if key == "peaks" and isinstance(item, list):
                for peak in item:
                    if isinstance(peak, Mapping):
                        row = _pick_compact(peak, _PEAK_FIELDS)
                        if row:
                            output.append(row)
                continue
            _collect_peaks(item, output)
    elif isinstance(value, list) and len(value) <= 16:
        for item in value:
            _collect_peaks(item, output)


def _deduplicate_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    unique: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        normalized = to_builtin(dict(row))
        key = _canonical_json(normalized)
        if key in seen:
            continue
        seen.add(key)
        unique.append(normalized)
    return unique


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _pick_compact(
    source: Mapping[str, Any],
    keys: Sequence[str],
) -> dict[str, Any]:
    return {
        key: to_builtin(source[key])
        for key in keys
        if key in source and _is_compact_value(source[key])
    }


def _compact_scalar_mapping(value: Any, *, limit: int = 20) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    compact: dict[str, Any] = {}
    for key in sorted(value):
        item = value[key]
        if _is_compact_value(item):
            compact[str(key)] = to_builtin(item)
        if len(compact) >= limit:
            break
    return compact


def _compact_nested_scalars(
    value: Mapping[str, Any],
    *,
    depth: int = 0,
    limit: int = 12,
) -> dict[str, Any]:
    if depth > 1:
        return {}
    compact: dict[str, Any] = {}
    for key in sorted(value):
        if str(key).lower() in _SKIPPED_ARRAY_KEYS or key == "peaks":
            continue
        item = value[key]
        if _is_compact_value(item):
            compact[str(key)] = to_builtin(item)
        elif isinstance(item, Mapping):
            nested = _compact_nested_scalars(item, depth=depth + 1, limit=limit)
            if nested:
                compact[str(key)] = nested
        if len(compact) >= limit:
            break
    return compact


def _active_flags(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return {
        str(key): to_builtin(item)
        for key, item in value.items()
        if item not in (None, False, 0, "", [], {}) and _is_compact_value(item)
    }


def _is_compact_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, bool | int | float):
        return True
    if isinstance(value, str):
        return len(value) <= 400
    if isinstance(value, list | tuple):
        return len(value) <= 12 and all(_is_compact_value(item) for item in value)
    return False


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


__all__ = [
    "DEFAULT_PROMPT_TOKEN_ESTIMATE_CAP",
    "PROMPT_CONTEXT_VERSION",
    "PromptBudgetExceededError",
    "PromptPacket",
    "build_decision_prompt",
    "compact_action",
    "compact_decision",
    "compact_experiment_memory",
    "estimate_prompt_segments",
    "estimate_prompt_tokens",
    "serialize_prompt_payload",
    "summarize_measurement",
]
