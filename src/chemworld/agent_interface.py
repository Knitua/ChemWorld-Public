"""Agent-facing public views for ChemWorld environments.

The functions in this module are intentionally thin adapters over the existing
task registry, operation validator, observation contracts, and campaign state.
They do not read hidden ledgers or rate constants.
"""

from __future__ import annotations

import math
from copy import deepcopy
from typing import Any

import numpy as np

from chemworld.data.logging import to_builtin
from chemworld.envs.spaces import OBSERVATION_KEYS
from chemworld.foundation import equipment_settings
from chemworld.materials import material_choice_labels
from chemworld.operation_validator import (
    ELECTROCHEMICAL_MIN_ADAPTED_CURRENT_DELTA_MA,
    ELECTROCHEMICAL_MIN_ADAPTED_POTENTIAL_DELTA_V,
)
from chemworld.physchem.crystallization_units import (
    DEFAULT_MAXIMUM_COOLING_RATE_K_S,
)
from chemworld.physchem.electrochemical_task_contract import (
    ELECTROCHEMICAL_WORKFLOW_AUTONOMOUS_OPEN_V1,
)
from chemworld.world.actions import CATALYSTS, ELECTROLYTE_PROFILES, SOLVENTS
from chemworld.world.operations import (
    CAMPAIGN_CONTROL_OPERATIONS,
    INSTRUMENTS,
    OPERATION_FIELD_BOUNDS,
    OPERATION_FIELD_CHOICES,
    OPERATION_TYPES,
    operation_contracts,
)

PUBLIC_ACTION_SCHEMA_VERSION = "chemworld-public-action-affordance-0.2"

FIELD_UNITS: dict[str, str] = {
    "amount_mol": "mol",
    "volume_L": "L",
    "catalyst_amount_mol": "mol",
    "target_temperature_K": "K",
    "duration_s": "s",
    "stirring_speed_rpm": "rpm",
    "sample_volume_L": "L",
    "wash_volume_L": "L",
    "transfer_fraction": "dimensionless",
    "seed_mass_g": "g",
    "reflux_ratio": "dimensionless",
    "flow_rate_mL_min": "mL/min",
    "residence_time_s": "s",
    "potential_V": "V",
    "current_mA": "mA",
    "instrument": "categorical",
    "catalyst": "categorical",
    "solvent": "categorical",
    "phase": "categorical",
    "target_phase": "categorical",
    "extractant": "categorical",
    "reason": "text",
}

FIELD_RANGES: dict[str, tuple[float, float]] = {
    "amount_mol": (0.0, 0.040),
    "volume_L": (0.0, 0.080),
    "catalyst_amount_mol": (0.0, 0.005),
    "target_temperature_K": (250.0, 520.0),
    "duration_s": (0.0, 14_400.0),
    "stirring_speed_rpm": (100.0, 1200.0),
    "sample_volume_L": (0.0, 0.002),
    "wash_volume_L": (0.0, 0.040),
    "transfer_fraction": (0.0, 1.0),
    "seed_mass_g": (0.0, 1.0),
    "reflux_ratio": (0.0, 10.0),
    "flow_rate_mL_min": (0.01, 20.0),
    "residence_time_s": (1.0, 7200.0),
    "potential_V": (-3.0, 3.0),
    "current_mA": (0.0, 500.0),
}

FIELD_CHOICES: dict[str, list[Any]] = {
    "instrument": list(INSTRUMENTS),
    "catalyst": list(range(len(CATALYSTS))),
    "solvent": list(range(len(SOLVENTS))),
    "phase": ["aqueous", "organic"],
    "target_phase": ["aqueous", "organic"],
    "extractant": list(range(len(SOLVENTS))),
    "electrolyte_profile": list(range(len(ELECTROLYTE_PROFILES))),
}

OPERATION_GROUPS: dict[str, tuple[str, ...]] = {
    "reaction_setup": ("add_solvent", "add_reagent", "add_catalyst"),
    "reaction_control": ("heat", "wait", "quench", "terminate"),
    "sampling_and_measurement": ("sample", "measure"),
    "phase_setup": ("add_phase", "add_extractant"),
    "phase_partition": ("mix", "settle", "separate_phase"),
    "purification": ("transfer", "wash", "dry", "concentrate"),
    "equilibrium_characterization": ("measure", "terminate"),
}

TASK_PROMPT_PROFILES: dict[str, dict[str, Any]] = {
    "reaction-to-assay": {
        "task_goal": (
            "Run one complete reaction experiment from charging the reactor to a "
            "valid terminal final assay."
        ),
        "success_criteria": [
            "Reach a valid final_assay after a physically legal operation sequence.",
            "Improve final_assay_score while keeping the trajectory valid.",
            "Use intermediate instruments only when their information is worth the cost.",
        ],
        "constraints": [
            "Single-experiment task: final_assay ends the episode.",
            "Terminate or quench before requesting final_assay.",
            "Heating before adding solvent/reagent/catalyst is invalid.",
        ],
        "measurement_policy": (
            "HPLC, GC, and UV-vis are noisy intermediate tools; final_assay is the "
            "high-cost terminal measurement used for the task result."
        ),
        "recommended_strategy": [
            "Charge solvent and reagent first, then add catalyst if used.",
            "Choose a temperature/time pair, run heat or wait, then inspect with HPLC/UV-vis.",
            "Terminate and run final_assay only after the reaction has meaningful conversion.",
        ],
        "failure_modes": [
            "precondition failure",
            "budget exhaustion before final_assay",
            "unsafe high-temperature or high-risk trajectory",
        ],
    },
    "reaction-to-purification": {
        "task_goal": (
            "Complete a reaction, extract product through phase separation, purify "
            "the material, and submit a final assay."
        ),
        "success_criteria": [
            "Maximize score while balancing purity, recovery, and cost.",
            "Keep process_mass_balance_error small through separation and purification.",
            "Use final_assay after downstream workup to make the result leaderboard eligible.",
        ],
        "constraints": [
            "Single-experiment task: final_assay ends the episode.",
            "Downstream purification should follow a terminated or quenched reaction.",
            "Phase operations require appropriate phase or extractant setup.",
        ],
        "measurement_policy": (
            "Intermediate HPLC/GC/UV-vis can guide reaction and workup choices. "
            "The final_assay should be run on the selected purified material."
        ),
        "recommended_strategy": [
            "First generate product under safe reaction conditions.",
            (
                "Add extractant or phase, mix, settle, and separate the phase "
                "expected to carry product."
            ),
            "Use wash/dry/concentrate to trade recovery against purity before final_assay.",
        ],
        "failure_modes": [
            "poor phase split",
            "low product recovery",
            "high impurity after purification",
            "mass-balance drift",
        ],
    },
    "electrochemical-conversion": {
        "task_goal": (
            "Use solvent-medium and electrolyte-profile comparisons plus pH/UV-vis "
            "diagnostics to adapt a second electrochemical regime."
        ),
        "success_criteria": [
            "Maximize selective_product_yield as the declared primary metric.",
            "Balance faradaic, transport, ohmic, and energy efficiency as secondary outcomes.",
            "Complete the probe, diagnostic, adapted-control, and final-assay lifecycle.",
        ],
        "constraints": [
            "Select one solvent and one electrolyte profile before the first electrolysis.",
            "After the probe, collect both ph_meter and uvvis diagnostics.",
            "The second setpoint must differ by at least 0.02 V or 1.0 mA.",
            "Only declared operation fields are accepted; cell physics is environment-owned.",
        ],
        "measurement_policy": (
            "ph_meter and uvvis expose noisy diagnostic consequences; final_assay is the "
            "leaderboard-grade outcome measurement."
        ),
        "recommended_strategy": [
            "Compare solvent and electrolyte choices relationally across experiments.",
            "Use the first regime as a probe, not as a duplicate production stage.",
            "Condition the second potential/current choice on the diagnostic response.",
        ],
        "failure_modes": [
            "repeating the probe setpoint",
            "terminating without the post-control UV-vis assay",
            "confounding solvent and electrolyte effects without matched controls",
        ],
    },
    "partition-discovery": {
        "task_goal": (
            "Learn the public behavior of an unknown product/solvent partition system "
            "through repeated finite-budget experiments."
        ),
        "success_criteria": [
            "Estimate phase_ratio from public observations.",
            "Identify when product is enriched in organic versus aqueous phase.",
            "Use measurements efficiently across campaign experiments.",
        ],
        "constraints": [
            (
                "Campaign task: one terminal assay or termination summarizes an "
                "experiment, not the whole campaign."
            ),
            "Partition coefficients and hidden phase amounts are not directly visible.",
            "Phase split actions require a valid phase setup, mixing, and settling sequence.",
        ],
        "measurement_policy": (
            "Use HPLC/GC/UV-vis/final_assay as public instruments to infer partition "
            "trends; do not assume hidden partition coefficients are known."
        ),
        "recommended_strategy": [
            "Vary solvent or extractant choices across experiments.",
            "Use mix and settle before separating phases.",
            (
                "Compare instrument summaries from organic and aqueous outcomes "
                "to build a local model."
            ),
        ],
        "failure_modes": [
            "insufficient phase setup",
            "separating before settling",
            "overusing costly measurements",
            "confusing noisy instrument estimates with hidden truth",
        ],
    },
    "equilibrium-characterization": {
        "task_goal": (
            "Characterize a bounded aqueous-equilibrium slice using pH-meter "
            "and final-assay observations."
        ),
        "success_criteria": [
            "Obtain informative pH-meter observations before final assay.",
            "Maximize equilibrium_confidence while keeping equilibrium_residual low.",
            "Use measurements efficiently under the finite campaign budget.",
        ],
        "constraints": [
            "pH is public only through ph_meter or final_assay observations.",
            "Hidden acidity constants and species amounts are never exposed.",
            "Final assay still requires terminate.",
        ],
        "measurement_policy": (
            "ph_meter is the low-cost primary characterization instrument. "
            "final_assay provides leaderboard-grade equilibrium metrics."
        ),
        "recommended_strategy": [
            "Charge solvent and a moderate reagent amount.",
            "Measure pH, perturb concentration, then measure pH again.",
            "Terminate and request final_assay after enough equilibrium evidence.",
        ],
        "failure_modes": [
            "measuring before material exists",
            "overusing final assay without intermediate evidence",
            "treating pH-normalized Gym scalar as hidden pKa",
        ],
    },
}

ELECTROCHEMICAL_AUTONOMOUS_OPEN_PROMPT_PROFILE: dict[str, Any] = {
    "task_goal": (
        "Autonomously design and execute electrochemical experiments by choosing "
        "materials, setpoints, electrolysis stages, and optional diagnostics to "
        "maximize the declared balanced leaderboard score."
    ),
    "success_criteria": [
        (
            "Optimize the full declared leaderboard contract; selective_product_yield "
            "has a gate and 0.30 weight but is not the sole objective."
        ),
        (
            "Balance selectivity, conversion, faradaic, transport, ohmic, and energy "
            "efficiency according to the published component weights."
        ),
        "Use repeated controls or measurements only when they advance the experiment.",
        "Complete each chosen experiment through terminate and final_assay.",
    ],
    "constraints": [
        "Material identities become locked when the corresponding physical fixture is charged.",
        "Terminate is legal only after at least one committed electrolysis.",
        "No diagnostic instrument, second stage, or setpoint change is mandatory.",
    ],
    "measurement_policy": (
        "ph_meter and uvvis are optional noisy diagnostics. final_assay is available "
        "only after terminate and completes the current experiment."
    ),
    "recommended_strategy": [
        "Use the current public affordances to identify physically legal operations.",
        "A valid final_assay after terminate completes the current experiment.",
        "All operations, including optional diagnostics, consume the finite campaign budget.",
    ],
    "failure_modes": [
        "terminating before electrolysis",
        "budget exhaustion before final_assay",
        "invalid material changes after the cell formulation is locked",
    ],
}

HIDDEN_INFORMATION_POLICY = (
    "No hidden species amounts, rate constants, mechanism parameters, partition "
    "coefficients, hidden phase amounts, or private scenario parameters are exposed "
    "through agent-facing views."
)

RL_MISSING_VALUE = -1.0
RL_OBSERVATION_VALUE_BOUNDS = (RL_MISSING_VALUE, 1.0)
RL_MASK_BOUNDS = (0.0, 1.0)
RL_COST_BOUNDS = (0.0, 1.0)

SUBMISSION_REQUIREMENTS = [
    "trajectory JSONL",
    "agent manifest",
    "reproducible command or replay trace",
]


def _base_env(env: Any) -> Any:
    return getattr(env, "unwrapped", env)


def _latest_info(env: Any) -> dict[str, Any]:
    base = _base_env(env)
    info = getattr(base, "_last_info", {})
    return deepcopy(info) if isinstance(info, dict) else {}


def _latest_observation(env: Any) -> dict[str, Any]:
    base = _base_env(env)
    observation = getattr(base, "_last_observation", {})
    return deepcopy(observation) if isinstance(observation, dict) else {}


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        scalar = float(value.reshape(-1)[0]) if isinstance(value, np.ndarray) else float(value)
    except (TypeError, ValueError, IndexError):
        return default
    return scalar if math.isfinite(scalar) else default


def _observed_float(value: Any) -> tuple[float, bool]:
    try:
        scalar = float(value.reshape(-1)[0]) if isinstance(value, np.ndarray) else float(value)
    except (TypeError, ValueError, IndexError):
        return -1.0, False
    return (scalar, True) if math.isfinite(scalar) else (-1.0, False)


def _field_schema(
    field: str,
    *,
    operation: str | None = None,
    task_id: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "field": field,
        "unit": FIELD_UNITS.get(field, "unitless"),
        "required": True,
    }
    bounds = OPERATION_FIELD_BOUNDS.get((operation, field)) if operation is not None else None
    if bounds is None:
        bounds = FIELD_RANGES.get(field)
    if bounds is not None:
        low, high = bounds
        payload["bounds"] = {"low": low, "high": high}
        payload["recommended_range"] = {"low": low, "high": high}
        payload["lower_bound_inclusive"] = not (
            field in {"amount_mol", "catalyst_amount_mol", "sample_volume_L"}
            or (field == "volume_L" and operation in {"add_solvent", "add_phase", "add_extractant"})
        )
        payload["upper_bound_inclusive"] = True
    operation_choices = (
        OPERATION_FIELD_CHOICES.get((operation, field)) if operation is not None else None
    )
    choices = list(operation_choices) if operation_choices is not None else FIELD_CHOICES.get(field)
    if choices is not None:
        payload["choices"] = list(choices)
        labels = material_choice_labels(field, task_id=task_id)
        if labels:
            payload["choice_labels"] = labels
    return payload


def _locked_recipe_choice(base: Any, operation: str, field: str) -> Any | None:
    lock_contract = {
        "add_solvent": ("solvent", "batch_reactor", "solvent_volume_L"),
        "add_catalyst": ("catalyst", "batch_reactor", "catalyst_amount_mol"),
        "add_extractant": (
            "extractant",
            "liquid_liquid_extractor",
            "extractant_volume_L",
        ),
    }.get(operation)
    if lock_contract is None:
        return None
    category_field, equipment_id, charged_key = lock_contract
    if field != category_field:
        return None
    state = getattr(base, "_state", None)
    if state is None:
        return None
    settings = equipment_settings(state.equipment, equipment_id)
    if float(settings.get(charged_key, 0.0)) <= 0.0:
        return None
    return settings.get(field)


def action_schema(env: Any, operation: str) -> dict[str, Any]:
    """Return the public JSON-friendly schema for one operation."""

    base = _base_env(env)
    contracts = operation_contracts(
        include_campaign_controls=operation in CAMPAIGN_CONTROL_OPERATIONS
    )
    if operation not in contracts:
        return {
            "schema_version": PUBLIC_ACTION_SCHEMA_VERSION,
            "operation": operation,
            "valid_operation_type": False,
            "error": f"Unknown operation {operation!r}",
        }
    contract = contracts[operation]
    state = getattr(base, "_state", None)
    task_id = getattr(base, "task_id", None)
    fields = [
        _field_schema(field, operation=operation, task_id=task_id)
        for field in contract.required_fields
    ]
    if operation == "measure":
        allowed_instruments = getattr(base, "allowed_instruments", set(INSTRUMENTS))
        fields = [
            {
                **_field_schema(
                    "instrument",
                    operation=operation,
                    task_id=task_id,
                ),
                "choices": [
                    instrument_id
                    for instrument_id in INSTRUMENTS
                    if instrument_id in allowed_instruments
                ],
            }
        ]
    for field in fields:
        field_name = str(field["field"])
        bounds = field.get("bounds")
        if isinstance(bounds, dict) and state is not None:
            low, high = base.operation_validator.public_field_bounds(
                operation,
                field_name,
                state,
                low=float(bounds["low"]),
                high=float(bounds["high"]),
            )
            if low != float(bounds["low"]) or high != float(bounds["high"]):
                field["bounds"] = {"low": low, "high": high}
                field["recommended_range"] = {"low": low, "high": high}
                field["state_dependent_bounds"] = True
        choices = field.get("choices")
        if isinstance(choices, list) and state is not None:
            public_choices = list(
                base.operation_validator.public_field_choices(
                    operation,
                    field_name,
                    state,
                    choices=tuple(choices),
                )
            )
            if public_choices != choices:
                field["choices"] = public_choices
                field["state_dependent_choices"] = True
        locked = _locked_recipe_choice(base, operation, field_name)
        if locked is not None:
            field["choices"] = [locked]
            field["locked_for_current_experiment"] = True
    _apply_campaign_resource_schema(base, operation, fields)
    constraints: list[dict[str, Any]] = []
    if operation == "cool_crystallize" and state is not None:
        constraints.extend(
            [
                {
                    "id": "cool_crystallize_requires_reaction_or_seed",
                    "kind": "state_precondition",
                    "description": (
                        "Requires at least one committed reaction advance or a seed charge."
                    ),
                },
                {
                    "id": "payload_coupling:maximum_cooling_rate_K_s",
                    "kind": "cross_field_upper_bound",
                    "fields": ["target_temperature_K", "duration_s"],
                    "relation": (
                        "(current_temperature_K - target_temperature_K) / duration_s "
                        "<= maximum_cooling_rate_K_s"
                    ),
                    "parameters": {
                        "current_temperature_K": float(state.temperature_K),
                        "maximum_cooling_rate_K_s": DEFAULT_MAXIMUM_COOLING_RATE_K_S,
                    },
                },
            ]
        )
    if operation == "set_potential":
        constraints.append(
            {
                "id": "payload_coupling:potential_within_voltage_window",
                "kind": "absolute_value_upper_bound",
                "fields": ["potential_V"],
                "relation": "abs(potential_V) <= default_voltage_window_V",
                "parameters": {"default_voltage_window_V": 2.5},
            }
        )
        if state is not None:
            cell_settings = equipment_settings(state.equipment, "electrochemical_cell")
            setpoint_history = tuple(cell_settings.get("setpoint_history", ()))
            if (
                len(setpoint_history) == 1
                and getattr(base, "electrochemical_workflow_mode", None)
                != ELECTROCHEMICAL_WORKFLOW_AUTONOMOUS_OPEN_V1
            ):
                constraints.append(
                    {
                        "id": "payload_adapts:electrochemical_setpoint",
                        "kind": "minimum_change_from_previous",
                        "fields": ["potential_V", "current_mA"],
                        "relation": (
                            "abs(potential_V - previous_potential_V) >= "
                            "minimum_potential_delta_V or "
                            "abs(current_mA - previous_current_mA) >= "
                            "minimum_current_delta_mA"
                        ),
                        "parameters": {
                            "previous_potential_V": float(dict(setpoint_history[0])["potential_V"]),
                            "previous_current_mA": float(dict(setpoint_history[0])["current_mA"]),
                            "minimum_potential_delta_V": (
                                ELECTROCHEMICAL_MIN_ADAPTED_POTENTIAL_DELTA_V
                            ),
                            "minimum_current_delta_mA": (
                                ELECTROCHEMICAL_MIN_ADAPTED_CURRENT_DELTA_MA
                            ),
                        },
                    }
                )
    return {
        "schema_version": PUBLIC_ACTION_SCHEMA_VERSION,
        "operation": operation,
        "valid_operation_type": True,
        "module": contract.module,
        "kind": contract.kind,
        "required_fields": list(contract.required_fields),
        "fields": fields,
        "preconditions": list(contract.preconditions),
        "constraints": constraints,
        "task_allowed": operation in getattr(base, "allowed_operations", set(OPERATION_TYPES)),
        "notes": [
            "Use validate_action(action) before executing.",
            "Payload aliases are canonicalized by the environment action codec.",
            "Fields outside operation and required_fields are rejected atomically.",
        ],
    }


def validate_action(env: Any, action: dict[str, Any]) -> dict[str, Any]:
    """Validate an action against schema, task policy, instrument policy, and state."""

    base = _base_env(env)
    try:
        canonical = base.action_codec.canonicalize(action)
    except (TypeError, ValueError) as exc:
        return {
            "operation_type": str(action.get("operation", "invalid")),
            "valid": False,
            "dispatchable_to_runtime": False,
            "preconditions": {"action_schema_valid": False},
            "invalid_reasons": [str(exc)],
            "valid_operations": list(base.operation_validator.valid_operations(base._state)),
            "action_mask": list(base.operation_validator.action_mask(base._state)),
            "cost_penalty": 0.20,
            "safety_flags": {
                "operation_allowed_by_task": False,
                "precondition_failed": True,
                "action_schema_valid": False,
            },
            "canonical_action": to_builtin(action),
            "will_mutate_state": False,
        }
    validation = base.operation_validator.validate(canonical, base._state)
    payload = validation.to_dict()
    resource_reasons = _campaign_resource_rejection_reasons_for_action(
        base,
        canonical,
    )
    if resource_reasons:
        payload["valid"] = False
        payload["dispatchable_to_runtime"] = False
        payload["preconditions"] = {
            **payload.get("preconditions", {}),
            "campaign_resources_available": False,
        }
        payload["invalid_reasons"] = list(
            dict.fromkeys(
                [
                    *payload.get("invalid_reasons", []),
                    "campaign_resources_available",
                    *[f"campaign_resource:{reason}" for reason in resource_reasons],
                ]
            )
        )
        payload["safety_flags"] = {
            **payload.get("safety_flags", {}),
            "precondition_failed": True,
            "campaign_resource_rejected": True,
        }
    payload["canonical_action"] = to_builtin(canonical)
    payload["will_mutate_state"] = False
    return to_builtin(payload)


def available_actions(env: Any, *, include_invalid: bool = False) -> list[dict[str, Any]]:
    """Return current operation affordances for agents and tool planners."""

    base = _base_env(env)
    valid = set(base.operation_validator.valid_operations(base._state))
    allowed = set(getattr(base, "allowed_operations", set(OPERATION_TYPES)))
    actions: list[dict[str, Any]] = []
    operation_types = tuple(getattr(base.operation_validator, "operation_types", OPERATION_TYPES))
    for operation in operation_types:
        if operation not in allowed and not include_invalid:
            continue
        if operation == "discard_batch":
            discard_available = getattr(
                base,
                "_campaign_batch_discard_available",
                lambda: False,
            )()
            if not discard_available and not include_invalid:
                continue
        affordance = base.operation_validator.operation_affordance(operation, base._state)
        validation = affordance.to_dict()
        schema = action_schema(base, operation)
        resource_reasons = list(
            _campaign_resource_rejection_reasons_for_operation(base, operation)
        )
        resource_reasons.extend(
            _campaign_schema_resource_rejection_reasons(base, operation, schema)
        )
        resource_reasons = list(dict.fromkeys(resource_reasons))
        is_valid = operation in valid and not resource_reasons
        if resource_reasons:
            validation["preconditions"] = {
                **validation["preconditions"],
                "campaign_resources_available": False,
            }
            validation["invalid_reasons"] = list(
                dict.fromkeys(
                    [
                        *validation["invalid_reasons"],
                        "campaign_resources_available",
                        *[f"campaign_resource:{reason}" for reason in resource_reasons],
                    ]
                )
            )
        if not is_valid and not include_invalid:
            continue
        actions.append(
            {
                "operation": operation,
                "valid": is_valid,
                "invalid_reasons": validation["invalid_reasons"],
                "preconditions": validation["preconditions"],
                "schema": schema,
            }
        )
    return actions


_CAMPAIGN_RESOURCE_STOCK_FIELDS: dict[str, tuple[str, str]] = {
    "add_reagent": ("reagent_mol", "amount_mol"),
    "add_solvent": ("solvent_L", "volume_L"),
    "add_catalyst": ("catalyst_mol", "catalyst_amount_mol"),
    "seed_crystals": ("seed_g", "seed_mass_g"),
    "add_extractant": ("extractant_L", "volume_L"),
    "add_phase": ("phase_liquid_L", "volume_L"),
    "wash": ("wash_solvent_L", "wash_volume_L"),
}


def _campaign_ledger(base: Any) -> Any | None:
    ledger = getattr(base, "_campaign_resource_ledger", None)
    return ledger


def _campaign_remaining(base: Any) -> dict[str, Any]:
    ledger = _campaign_ledger(base)
    if ledger is None:
        return {}
    snapshot = ledger.snapshot()
    state = snapshot.get("state", {})
    remaining = state.get("remaining", {})
    return dict(remaining) if isinstance(remaining, dict) else {}


def _campaign_starts_vessel(base: Any, operation: str) -> bool:
    return bool(
        operation != "discard_batch"
        and not getattr(base, "_campaign_resource_current_vessel_started", False)
    )


def _campaign_resource_rejection_reasons_for_action(
    base: Any,
    action: dict[str, Any],
) -> tuple[str, ...]:
    ledger = _campaign_ledger(base)
    if ledger is None:
        return ()
    operation = str(action.get("operation", ""))
    if not operation:
        return ()
    return ledger.preview_rejection_reasons(
        action,
        starts_vessel=_campaign_starts_vessel(base, operation),
    )


def _campaign_measure_resource_choices(
    base: Any,
    choices: list[Any],
) -> tuple[list[Any], tuple[str, ...]]:
    ledger = _campaign_ledger(base)
    if ledger is None:
        return choices, ()
    remaining = _campaign_remaining(base)
    nonfinal_remaining = int(remaining.get("nonfinal_instrument_uses", 0))
    final_remaining = int(remaining.get("final_assays", 0))
    per_instrument = remaining.get("per_instrument", {})
    if not isinstance(per_instrument, dict):
        per_instrument = {}
    filtered: list[Any] = []
    rejected: list[str] = []
    for instrument in choices:
        if instrument == "final_assay":
            if final_remaining < 1:
                rejected.append("final_assay_limit")
                continue
        else:
            if nonfinal_remaining < 1:
                rejected.append("nonfinal_instrument_use_limit")
                continue
            instrument_remaining = per_instrument.get(instrument)
            if instrument_remaining is not None and int(instrument_remaining) < 1:
                rejected.append(f"per_instrument_limit:{instrument}")
                continue
        filtered.append(instrument)
    return filtered, tuple(dict.fromkeys(rejected))


def _campaign_resource_rejection_reasons_for_operation(
    base: Any,
    operation: str,
) -> tuple[str, ...]:
    ledger = _campaign_ledger(base)
    if ledger is None:
        return ()
    remaining = _campaign_remaining(base)
    reasons: list[str] = []
    if int(remaining.get("operation_attempts", 0)) < 1:
        reasons.append("operation_attempt_limit")
    if _campaign_starts_vessel(base, operation) and int(
        remaining.get("vessel_starts", 0)
    ) < 1:
        reasons.append("vessel_start_limit")
    if operation == "measure":
        schema_choices = [
            instrument
            for instrument in INSTRUMENTS
            if instrument in getattr(base, "allowed_instruments", set(INSTRUMENTS))
        ]
        state = getattr(base, "_state", None)
        if state is not None:
            schema_choices = list(
                base.operation_validator.public_field_choices(
                    operation,
                    "instrument",
                    state,
                    choices=tuple(schema_choices),
                )
            )
        filtered_choices, measure_reasons = _campaign_measure_resource_choices(
            base,
            schema_choices,
        )
        if not filtered_choices:
            reasons.extend(measure_reasons or ("measurement_resource_limit",))
    stock_contract = _CAMPAIGN_RESOURCE_STOCK_FIELDS.get(operation)
    if stock_contract is not None:
        stock_id, _ = stock_contract
        if stock_id not in ledger.card.stock_limits:
            return tuple(dict.fromkeys(reasons))
        stocks = remaining.get("stocks", {})
        available = float(stocks.get(stock_id, 0.0)) if isinstance(stocks, dict) else 0.0
        if available <= 1.0e-12:
            reasons.append(f"stock_limit:{stock_id}")
    return tuple(dict.fromkeys(reasons))


def _campaign_schema_resource_rejection_reasons(
    base: Any,
    operation: str,
    schema: dict[str, Any],
) -> tuple[str, ...]:
    """Detect empty resource-constrained numeric domains in a public schema."""

    ledger = _campaign_ledger(base)
    if ledger is None:
        return ()
    stock_contract = _CAMPAIGN_RESOURCE_STOCK_FIELDS.get(operation)
    if stock_contract is None:
        return ()
    stock_id, field_name = stock_contract
    if stock_id not in ledger.card.stock_limits:
        return ()
    remaining = _campaign_remaining(base)
    stocks = remaining.get("stocks", {})
    available = float(stocks.get(stock_id, 0.0)) if isinstance(stocks, dict) else 0.0
    for field in schema.get("fields", []):
        if not isinstance(field, dict) or field.get("field") != field_name:
            continue
        bounds = field.get("bounds")
        if not isinstance(bounds, dict):
            continue
        low = float(bounds.get("low", 0.0))
        high = float(bounds.get("high", 0.0))
        if available <= 1.0e-12 or high <= low + 1.0e-12:
            return (f"stock_limit:{stock_id}",)
    return ()


def _apply_campaign_resource_schema(
    base: Any,
    operation: str,
    fields: list[dict[str, Any]],
) -> None:
    """Narrow G2 schemas to the remaining public campaign envelope."""

    ledger = _campaign_ledger(base)
    if ledger is None:
        return
    remaining = _campaign_remaining(base)
    stock_contract = _CAMPAIGN_RESOURCE_STOCK_FIELDS.get(operation)
    stock_remaining: float | None = None
    if stock_contract is not None:
        stock_id, _ = stock_contract
        if stock_id in ledger.card.stock_limits:
            stocks = remaining.get("stocks", {})
            if isinstance(stocks, dict):
                stock_remaining = max(float(stocks.get(stock_id, 0.0)), 0.0)
    for field in fields:
        field_name = str(field.get("field", ""))
        if (
            stock_contract is not None
            and stock_remaining is not None
            and field_name == stock_contract[1]
        ):
            bounds = field.get("bounds")
            if isinstance(bounds, dict) and stock_remaining is not None:
                old_high = float(bounds.get("high", stock_remaining))
                new_high = min(old_high, stock_remaining)
                field["bounds"] = {
                    "low": float(bounds.get("low", 0.0)),
                    "high": new_high,
                }
                field["recommended_range"] = {
                    "low": float(bounds.get("low", 0.0)),
                    "high": new_high,
                }
                field["state_dependent_bounds"] = True
                field["resource_limited"] = new_high < old_high
        if operation == "measure" and field_name == "instrument":
            choices = field.get("choices")
            if isinstance(choices, list):
                filtered, _ = _campaign_measure_resource_choices(base, choices)
                field["choices"] = filtered
                if filtered != choices:
                    field["resource_limited"] = True


def _task_spec_value(base: Any, name: str, fallback: Any = None) -> Any:
    spec = getattr(base, "task_spec", None)
    if spec is None:
        return fallback
    return getattr(spec, name, fallback)


def _allowed_operation_groups(allowed_operations: list[str]) -> dict[str, list[str]]:
    allowed = set(allowed_operations)
    groups: dict[str, list[str]] = {}
    grouped: set[str] = set()
    for group, operations in OPERATION_GROUPS.items():
        present = [operation for operation in operations if operation in allowed]
        if present:
            groups[group] = present
            grouped.update(present)
    other = sorted(allowed - grouped)
    if other:
        groups["other"] = other
    return groups


def _default_task_prompt_profile(info: dict[str, Any], base: Any) -> dict[str, Any]:
    description = _task_spec_value(
        base,
        "description",
        info.get("description") or "Run the ChemWorld task under the public contract.",
    )
    return {
        "task_goal": description,
        "success_criteria": [
            "Optimize the public task score under the stated budget and constraints.",
            "Use only task-allowed operations and instruments.",
            "Submit a replayable trajectory with public observations and constraint flags.",
        ],
        "constraints": [
            f"Episode mode: {info.get('episode_mode')}.",
            f"Safety limit: {info.get('safety_limit')}.",
            "Measurements are noisy and consume time, sample, or cost.",
        ],
        "measurement_policy": (
            "Use available instruments to obtain public observations. Instrument "
            "outputs are partial, noisy, and cost-aware."
        ),
        "recommended_strategy": [
            "Validate actions before executing them.",
            "Use measurements to update a local world model.",
            "Balance score, cost, risk, and remaining budget.",
        ],
        "failure_modes": [
            "invalid operation",
            "precondition failure",
            "budget exhaustion",
            "unsafe or high-cost trajectory",
        ],
    }


def _task_prompt_profile(info: dict[str, Any], base: Any) -> dict[str, Any]:
    task_id = str(info.get("task_id") or "")
    if (
        task_id == "electrochemical-conversion"
        and getattr(base, "electrochemical_workflow_mode", None)
        == ELECTROCHEMICAL_WORKFLOW_AUTONOMOUS_OPEN_V1
    ):
        return ELECTROCHEMICAL_AUTONOMOUS_OPEN_PROMPT_PROFILE
    if task_id in TASK_PROMPT_PROFILES:
        return TASK_PROMPT_PROFILES[task_id]
    return _default_task_prompt_profile(info, base)


def experiment_lifecycle_contract(episode_mode: Any) -> dict[str, str]:
    """Describe experiment completion without prescribing a search strategy."""

    final_effect = (
        "A valid final_assay completes the current experiment and, while campaign "
        "budget remains, resets the environment to a fresh experiment."
        if episode_mode == "campaign"
        else "A valid final_assay completes the experiment and ends the episode."
    )
    return {
        "terminate_effect": (
            "terminate marks the current process as terminated; it does not by itself "
            "complete the experiment."
        ),
        "final_assay_precondition": (
            "measure with instrument=final_assay is valid only after terminate."
        ),
        "final_assay_effect": final_effect,
        "intermediate_measurement_effect": (
            "Measurements with other instruments provide evidence but do not complete "
            "the experiment."
        ),
        "discard_batch_effect": (
            "In campaign mode, discard_batch is an explicit Agent decision that ends "
            "the current open batch without returning consumed resources; a fresh batch "
            "is exposed only when the campaign ledger still permits it."
            if episode_mode == "campaign"
            else "discard_batch is unavailable outside campaign mode."
        ),
    }


def _render_task_prompt_text(
    *,
    task_id: str,
    objective: Any,
    budget: Any,
    episode_mode: Any,
    safety_limit: Any,
    profile: dict[str, Any],
    allowed_operations: list[str],
    allowed_instruments: list[str],
    success_metrics: list[str],
    operation_groups: dict[str, list[str]],
    experiment_lifecycle: dict[str, str],
) -> str:
    group_lines = [
        f"  - {group}: {', '.join(operations)}" for group, operations in operation_groups.items()
    ]
    lines = [
        f"Task: {task_id or 'ad-hoc ChemWorld task'}",
        f"Goal: {profile['task_goal']}",
        (
            f"Objective: {objective}; budget: {budget} operations; "
            f"episode_mode: {episode_mode}; safety_limit: {safety_limit}."
        ),
        "Hidden information policy: " + HIDDEN_INFORMATION_POLICY,
        "Success criteria:",
        *[f"  - {item}" for item in profile["success_criteria"]],
        "Constraints:",
        *[f"  - {item}" for item in profile["constraints"]],
        "Experiment lifecycle:",
        *[f"  - {item}" for item in experiment_lifecycle.values()],
        "Allowed tools:",
        f"  - instruments: {', '.join(allowed_instruments)}",
        "  - operation groups:",
        *group_lines,
        f"  - all operations: {', '.join(allowed_operations)}",
        f"Success metrics: {', '.join(success_metrics) if success_metrics else 'task score'}.",
        f"Measurement policy: {profile['measurement_policy']}",
        "Recommended strategy:",
        *[f"  - {item}" for item in profile["recommended_strategy"]],
        "Submission requirements: " + ", ".join(SUBMISSION_REQUIREMENTS) + ".",
    ]
    return "\n".join(lines)


def task_prompt(env: Any) -> dict[str, Any]:
    """Build a natural-language task prompt plus structured task facts."""

    base = _base_env(env)
    info = base.task_info()
    allowed_operations = list(info.get("allowed_operations", []))
    allowed_instruments = list(info.get("allowed_instruments", []))
    success_metrics = list(
        info.get("scoring_contract", {}).get("success_metrics")
        or _task_spec_value(base, "success_metrics", ())
        or []
    )
    operation_groups = _allowed_operation_groups(allowed_operations)
    profile = _task_prompt_profile(info, base)
    experiment_lifecycle = experiment_lifecycle_contract(info.get("episode_mode"))
    task_id = str(info.get("task_id") or "")
    text = _render_task_prompt_text(
        task_id=task_id,
        objective=info.get("objective"),
        budget=info.get("budget"),
        episode_mode=info.get("episode_mode"),
        safety_limit=info.get("safety_limit"),
        profile=profile,
        allowed_operations=allowed_operations,
        allowed_instruments=allowed_instruments,
        success_metrics=success_metrics,
        operation_groups=operation_groups,
        experiment_lifecycle=experiment_lifecycle,
    )
    return {
        "text": text,
        "task_id": info.get("task_id"),
        "objective": info.get("objective"),
        "budget": info.get("budget"),
        "episode_mode": info.get("episode_mode"),
        "description": _task_spec_value(base, "description", info.get("description")),
        "world_law_id": info.get("world_law_id"),
        "scenario_id": info.get("scenario_id"),
        "allowed_operations": info.get("allowed_operations", []),
        "allowed_instruments": info.get("allowed_instruments", []),
        "success_metrics": success_metrics,
        "safety_limit": info.get("safety_limit"),
        "threshold": _task_spec_value(base, "threshold", info.get("threshold")),
        "termination_policy": _task_spec_value(
            base,
            "termination_policy",
            info.get("termination_policy"),
        ),
        "observation_policy": _task_spec_value(
            base,
            "observation_policy",
            info.get("observation_policy"),
        ),
        "task_goal": profile["task_goal"],
        "constraints": list(profile["constraints"]),
        "success_criteria": list(profile["success_criteria"]),
        "allowed_tools": {
            "operations": allowed_operations,
            "operation_groups": operation_groups,
            "instruments": allowed_instruments,
        },
        "material_catalog": info.get("material_catalog", {}),
        "material_information": info.get("material_information"),
        **(
            {
                "campaign_resources": deepcopy(
                    info["campaign_resources"]
                )
            }
            if "campaign_resources" in info
            else {}
        ),
        "electrochemical_workflow_mode": info.get(
            "electrochemical_workflow_mode"
        ),
        "measurement_policy": profile["measurement_policy"],
        "experiment_lifecycle": experiment_lifecycle,
        "recommended_strategy": list(profile["recommended_strategy"]),
        "failure_modes": list(profile["failure_modes"]),
        "hidden_information_policy": HIDDEN_INFORMATION_POLICY,
        "submission_requirements": list(SUBMISSION_REQUIREMENTS),
        "prompt_version": "chemworld-agent-task-prompt-0.3",
    }


def campaign_state(env: Any) -> dict[str, Any]:
    """Return visible campaign progress and best-so-far state."""

    base = _base_env(env)
    summaries = deepcopy(getattr(base, "_experiment_summaries", []))
    completed_summaries = [
        summary for summary in summaries if summary.get("final_assay") is True
    ]
    scored = [
        _safe_float(summary.get("leaderboard_score"), default=-1.0)
        for summary in completed_summaries
        if summary.get("leaderboard_score") is not None
    ]
    info = _latest_info(base)
    current_score = info.get("leaderboard_score")
    current_score_already_summarized = bool(
        info.get("experiment_ended") and getattr(base, "episode_mode", None) == "campaign"
    )
    if current_score is not None and not current_score_already_summarized:
        scored.append(_safe_float(current_score, default=-1.0))
    best_score = max(scored) if scored else None
    remaining_budget = max(
        int(getattr(base, "budget", 0)) - int(getattr(base, "_step_count", 0)),
        0,
    )
    payload = {
        "campaign_id": getattr(base, "_campaign_id", None),
        "task_id": getattr(base, "task_id", None),
        "scenario_id": getattr(getattr(base, "scenario_spec", None), "scenario_id", None),
        "episode_mode": getattr(base, "episode_mode", None),
        "experiment_index": int(getattr(base, "_experiment_index", 0)),
        "operation_count": int(getattr(base, "_step_count", 0)),
        "remaining_budget": remaining_budget,
        "budget": int(getattr(base, "budget", 0)),
        "final_assay_count": len(completed_summaries)
        + (1 if current_score is not None and not current_score_already_summarized else 0),
        "best_score": best_score,
        "last_terminal_summary": summaries[-1] if summaries else None,
        "experiment_summaries": to_builtin(summaries),
        "completed_batches": to_builtin(completed_summaries),
        "discarded_batches": to_builtin(
            [summary for summary in summaries if summary.get("outcome") == "discarded"]
        ),
        "done": bool(getattr(base, "_done", False)),
    }
    resource_state_factory = getattr(
        base,
        "public_campaign_resource_state",
        None,
    )
    if callable(resource_state_factory):
        resources = resource_state_factory()
        if resources is not None:
            payload["campaign_resources"] = resources
    declared_process_factory = getattr(
        base,
        "public_declared_process_resource_state",
        None,
    )
    if callable(declared_process_factory):
        declared_process = declared_process_factory()
        if declared_process is not None:
            payload["declared_process_resources"] = declared_process
    return payload


def rl_observation_view(
    observation: dict[str, Any],
    info: dict[str, Any] | None = None,
    *,
    include_cost: bool = True,
) -> dict[str, Any]:
    """Return a NaN-safe vector observation and binary observed mask."""

    values: list[float] = []
    mask: list[float] = []
    for key in OBSERVATION_KEYS:
        value, observed = _observed_float(observation.get(key))
        values.append(value if observed else RL_MISSING_VALUE)
        mask.append(1.0 if observed else 0.0)
    if include_cost:
        values.append(_safe_float((info or {}).get("cost"), default=0.0))
        mask.append(1.0)
    spec = rl_observation_spec(include_cost=include_cost)
    return {
        "mode": "rl",
        "schema_version": "chemworld-rl-view-0.2",
        "keys": spec["keys"],
        "vector": values,
        "mask": mask,
        "cost": _safe_float((info or {}).get("cost"), default=0.0),
        "bounds": spec["value_bounds"],
        "mask_bounds": spec["mask_bounds"],
        "missing_value": RL_MISSING_VALUE,
        "dtype": "float32",
        "nan_safe": True,
        "constraint_flags": to_builtin((info or {}).get("constraint_flags", {})),
    }


def rl_observation_spec(*, include_cost: bool = True) -> dict[str, Any]:
    """Return the stable RL vector contract used by views and wrappers."""

    keys = [*OBSERVATION_KEYS, *(["cost_signal"] if include_cost else [])]
    low = [RL_OBSERVATION_VALUE_BOUNDS[0] for _ in OBSERVATION_KEYS]
    high = [RL_OBSERVATION_VALUE_BOUNDS[1] for _ in OBSERVATION_KEYS]
    if include_cost:
        low.append(RL_COST_BOUNDS[0])
        high.append(RL_COST_BOUNDS[1])
    return {
        "schema_version": "chemworld-rl-view-0.2",
        "keys": list(keys),
        "value_bounds": {
            "low": low,
            "high": high,
        },
        "mask_bounds": {
            "low": [RL_MASK_BOUNDS[0] for _ in keys],
            "high": [RL_MASK_BOUNDS[1] for _ in keys],
        },
        "missing_value": RL_MISSING_VALUE,
        "dtype": "float32",
        "nan_safe": True,
    }


def _peak_group(peak: dict[str, Any]) -> str:
    for key in ("public_role", "role", "group", "species_role", "species_id"):
        value = str(peak.get(key, "")).lower()
        if value:
            if "reactant" in value:
                return "reactant"
            if "byproduct" in value or "impurity" in value:
                return "impurity"
            if "degradation" in value:
                return "degradation"
            if "target" in value or "product" in value:
                return "target"
    return "unknown"


def _find_peak_tables(payload: Any) -> list[list[dict[str, Any]]]:
    if isinstance(payload, dict):
        tables: list[list[dict[str, Any]]] = []
        for key, value in payload.items():
            if key in {"peaks", "peak_table", "chromatogram"} and isinstance(value, list):
                dict_rows = [row for row in value if isinstance(row, dict)]
                if dict_rows:
                    tables.append(dict_rows)
            else:
                tables.extend(_find_peak_tables(value))
        return tables
    if isinstance(payload, list):
        tables = []
        for item in payload:
            tables.extend(_find_peak_tables(item))
        return tables
    return []


def _area_value(peak: dict[str, Any]) -> float:
    for key in ("area_fraction", "peak_fraction", "area", "height", "intensity"):
        if key in peak:
            return max(_safe_float(peak[key], default=0.0), 0.0)
    return 0.0


def spectra_summary(info: dict[str, Any]) -> dict[str, Any]:
    """Summarize public raw signals without exposing hidden mechanism identities."""

    raw_signal = info.get("raw_signal", {})
    raw_signal_dict = raw_signal if isinstance(raw_signal, dict) else {}
    spectra = raw_signal_dict.get("spectra", {})
    channels = raw_signal_dict.get("channels", [])
    if not isinstance(channels, list):
        channels = []
    if isinstance(spectra, dict) and not channels:
        channels = sorted(str(key) for key in spectra)
    peak_tables = _find_peak_tables(raw_signal)
    grouped: dict[str, float] = {
        "target": 0.0,
        "reactant": 0.0,
        "impurity": 0.0,
        "degradation": 0.0,
        "unknown": 0.0,
    }
    dominant_group: str | None = None
    dominant_fraction = 0.0
    total_area = 0.0
    for table in peak_tables:
        for peak in table:
            area = _area_value(peak)
            group = _peak_group(peak)
            grouped[group] = grouped.get(group, 0.0) + area
            total_area += area
    if total_area > 0.0:
        for group, value in list(grouped.items()):
            grouped[group] = value / total_area
        top_group, top_fraction = max(grouped.items(), key=lambda item: item[1])
        dominant_group = top_group
        dominant_fraction = top_fraction

    processed = info.get("processed_estimate", {})
    observed = info.get("observed_keys", [])
    warnings: list[str] = []
    if grouped["reactant"] > grouped["target"] and any(
        key in observed for key in ("yield", "purity", "recovery")
    ):
        warnings.append("reactant_peak_dominates_public_spectrum")
    if grouped["impurity"] + grouped["degradation"] > 0.35:
        warnings.append("impurity_or_degradation_peaks_are_large")

    return {
        "instrument": info.get("instrument_source") or info.get("instrument"),
        "packet_kind": raw_signal_dict.get("kind"),
        "has_spectral_packet": bool(
            peak_tables or spectra or channels or raw_signal_dict.get("kind") == "ph_meter_signal"
        ),
        "channels": [str(channel) for channel in channels],
        "channel_count": len(channels),
        "peak_table_count": len(peak_tables),
        "observed_keys": list(observed),
        "peak_group_fractions": grouped,
        "dominant_peak": {"group": dominant_group, "fraction": dominant_fraction},
        "processed_estimate": to_builtin(processed),
        "uncertainty": to_builtin(info.get("uncertainty", {})),
        "warnings": warnings,
    }


def _recovery_suggestion(env: Any, info: dict[str, Any]) -> str | None:
    flags = info.get("constraint_flags", {})
    if not flags.get("precondition_failed") and not info.get("error_message"):
        return None
    options = [entry["operation"] for entry in available_actions(env)]
    if options:
        return "Retry with a currently valid operation such as " + ", ".join(options[:4]) + "."
    return (
        "No valid operation is currently available; reset the environment or inspect task policy."
    )


def _visible_metrics(observation: dict[str, Any]) -> dict[str, float]:
    metrics: dict[str, float] = {}
    for key in OBSERVATION_KEYS:
        value, observed = _observed_float(observation.get(key))
        if observed:
            metrics[key] = value
    return metrics


def _format_metric_map(metrics: dict[str, float], keys: tuple[str, ...]) -> str:
    parts = [f"{key}={metrics[key]:.3f}" for key in keys if key in metrics]
    return ", ".join(parts) if parts else "none"


def _instrument_summary(info: dict[str, Any]) -> dict[str, Any]:
    instrument = info.get("instrument_source") or info.get("instrument")
    return {
        "operation_type": info.get("operation_type"),
        "instrument": instrument,
        "is_measurement": info.get("operation_type") == "measure",
        "observed_keys": to_builtin(info.get("observed_keys", [])),
        "measurement_cost": _safe_float(info.get("measurement_cost"), default=0.0),
        "sample_consumed": _safe_float(info.get("sample_consumed"), default=0.0),
        "reward_source": info.get("reward_source"),
    }


def _final_assay_summary(info: dict[str, Any], campaign: dict[str, Any]) -> dict[str, Any]:
    instrument = info.get("instrument_source") or info.get("instrument")
    is_final_assay = info.get("operation_type") == "measure" and instrument == "final_assay"
    leaderboard_score = info.get("leaderboard_score")
    return {
        "is_final_assay": is_final_assay,
        "leaderboard_score": (
            None if leaderboard_score is None else _safe_float(leaderboard_score)
        ),
        "leaderboard_eligible": bool(is_final_assay and leaderboard_score is not None),
        "experiment_ended": bool(info.get("experiment_ended", False)),
        "episode_done": bool(campaign.get("done", False)),
        "final_assay_count": campaign.get("final_assay_count", 0),
        "last_terminal_summary": to_builtin(campaign.get("last_terminal_summary")),
    }


def _campaign_progress(campaign: dict[str, Any]) -> dict[str, Any]:
    budget = max(int(campaign.get("budget") or 0), 0)
    operation_count = max(int(campaign.get("operation_count") or 0), 0)
    remaining = max(int(campaign.get("remaining_budget") or 0), 0)
    progress_fraction = operation_count / budget if budget > 0 else 0.0
    best_score = campaign.get("best_score")
    return {
        "campaign_id": campaign.get("campaign_id"),
        "task_id": campaign.get("task_id"),
        "episode_mode": campaign.get("episode_mode"),
        "experiment_index": campaign.get("experiment_index"),
        "operation_count": operation_count,
        "budget": budget,
        "remaining_budget": remaining,
        "progress_fraction": progress_fraction,
        "final_assay_count": campaign.get("final_assay_count", 0),
        "best_score": None if best_score is None else _safe_float(best_score),
        "done": bool(campaign.get("done", False)),
    }


def _failure_summary(info: dict[str, Any]) -> dict[str, Any]:
    flags = info.get("constraint_flags", {})
    preconditions = info.get("preconditions", {})
    failed_preconditions = [
        str(key) for key, passed in preconditions.items() if isinstance(passed, bool) and not passed
    ]
    return {
        "precondition_failed": bool(flags.get("precondition_failed", False)),
        "constitution_failed": bool(flags.get("constitution_failed", False)),
        "transaction_status": info.get("transaction_status"),
        "rollback_reason": info.get("rollback_reason"),
        "error_message": info.get("error_message"),
        "failed_preconditions": failed_preconditions,
    }


def _next_action_hints(env: Any, *, limit: int = 5) -> list[str]:
    return [entry["operation"] for entry in available_actions(env)[:limit]]


def lab_report_view(env: Any, observation: dict[str, Any], info: dict[str, Any]) -> dict[str, Any]:
    """Return a compact public lab report for LLMs and students."""

    summary = spectra_summary(info)
    campaign = campaign_state(env)
    progress = _campaign_progress(campaign)
    metrics = _visible_metrics(observation)
    instrument = _instrument_summary(info)
    final_assay = _final_assay_summary(info, campaign)
    failure = _failure_summary(info)
    score = _safe_float(observation.get("score"), default=0.0)
    cost = _safe_float(observation.get("cost"), default=0.0)
    risk = _safe_float(observation.get("safety_risk"), default=0.0)
    failed = failure["precondition_failed"]
    status = "failed_precondition" if failed else "accepted"
    lines = [
        f"Operation {info.get('operation_type') or 'none'} was {status}.",
        f"Visible score={score:.3f}, cost={cost:.3f}, safety_risk={risk:.3f}.",
        (
            "Key public metrics: "
            + _format_metric_map(
                metrics,
                (
                    "yield",
                    "selectivity",
                    "conversion",
                    "purity",
                    "recovery",
                    "phase_ratio",
                    "pH_normalized",
                    "acid_dissociation_fraction",
                    "precipitation_signal",
                    "equilibrium_residual",
                    "equilibrium_confidence",
                    "score",
                ),
            )
            + "."
        ),
        f"Observed keys: {', '.join(summary['observed_keys']) or 'none'}.",
        (
            f"Campaign progress: step {progress['operation_count']}/{progress['budget']}, "
            f"experiment {progress['experiment_index']}, "
            f"remaining {progress['remaining_budget']}, "
            f"final_assays {progress['final_assay_count']}."
        ),
    ]
    if instrument["instrument"] is not None:
        lines.append(
            f"Instrument: {instrument['instrument']} "
            f"(measurement_cost={instrument['measurement_cost']:.3f}, "
            f"sample={instrument['sample_consumed']:.6f})."
        )
    if final_assay["is_final_assay"]:
        score_text = (
            "none"
            if final_assay["leaderboard_score"] is None
            else f"{float(final_assay['leaderboard_score']):.3f}"
        )
        lines.append(
            "Final assay: leaderboard_eligible="
            f"{final_assay['leaderboard_eligible']}, score={score_text}."
        )
    if summary["has_spectral_packet"]:
        channels = ", ".join(summary["channels"]) or "public peaks"
        lines.append(
            f"Spectra packet: {summary['packet_kind'] or 'instrument_signal'} "
            f"with {summary['channel_count']} channels ({channels})."
        )
    dominant = summary["dominant_peak"]
    if dominant["group"] is not None:
        lines.append(
            f"Dominant public spectral group: {dominant['group']} "
            f"({float(dominant['fraction']):.2f})."
        )
    if summary["warnings"]:
        lines.append("Spectral warnings: " + ", ".join(summary["warnings"]) + ".")
    recovery = _recovery_suggestion(env, info)
    if recovery is not None:
        lines.append(f"Recovery suggestion: {recovery}")
    if campaign["best_score"] is not None:
        lines.append(f"Best score so far: {float(campaign['best_score']):.3f}.")
    return {
        "mode": "lab_report",
        "report_version": "chemworld-lab-report-0.2",
        "text": "\n".join(lines),
        "status": status,
        "operation_type": info.get("operation_type"),
        "visible_metrics": metrics,
        "instrument_summary": instrument,
        "final_assay_summary": final_assay,
        "spectra_summary": summary,
        "campaign_state": campaign,
        "campaign_progress": progress,
        "failure_summary": failure,
        "next_action_hints": _next_action_hints(env),
        "recovery_suggestion": recovery,
        "constraint_flags": to_builtin(info.get("constraint_flags", {})),
    }


def tool_json_view(env: Any, observation: dict[str, Any], info: dict[str, Any]) -> dict[str, Any]:
    """Return a structured public observation bundle for tool agents."""

    return {
        "mode": "tool_json",
        "task": {
            "task_id": getattr(_base_env(env), "task_id", None),
            "objective": getattr(_base_env(env), "objective", None),
        },
        "observation": to_builtin(observation),
        "raw_signal": to_builtin(info.get("raw_signal", {})),
        "processed_estimate": to_builtin(info.get("processed_estimate", {})),
        "uncertainty": to_builtin(info.get("uncertainty", {})),
        "observed_keys": to_builtin(info.get("observed_keys", [])),
        "observed_mask": to_builtin(info.get("observed_mask", {})),
        "cost": _safe_float(info.get("cost"), default=0.0),
        "cost_components": to_builtin(info.get("cost_components", {})),
        "constraints": to_builtin(info.get("constraint_flags", {})),
        "campaign_state": campaign_state(env),
        "available_actions": available_actions(env),
        "lab_report": lab_report_view(env, observation, info),
    }


def observation_view(
    env: Any,
    mode: str = "tool_json",
    observation: dict[str, Any] | None = None,
    info: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return an agent-facing observation view."""

    base = _base_env(env)
    obs = _latest_observation(base) if observation is None else observation
    step_info = _latest_info(base) if info is None else info
    if mode == "rl":
        return rl_observation_view(obs, step_info)
    if mode == "tool_json":
        return tool_json_view(base, obs, step_info)
    if mode == "lab_report":
        return lab_report_view(base, obs, step_info)
    raise ValueError("mode must be one of 'rl', 'tool_json', or 'lab_report'")


def agent_view_bundle(
    env: Any,
    observation: dict[str, Any],
    info: dict[str, Any],
) -> dict[str, Any]:
    """Return all standard agent-facing views for trajectory export."""

    return {
        "rl": observation_view(env, "rl", observation, info),
        "tool_json": observation_view(env, "tool_json", observation, info),
        "lab_report": observation_view(env, "lab_report", observation, info),
    }


__all__ = [
    "action_schema",
    "agent_view_bundle",
    "available_actions",
    "campaign_state",
    "lab_report_view",
    "observation_view",
    "rl_observation_spec",
    "rl_observation_view",
    "spectra_summary",
    "task_prompt",
    "tool_json_view",
    "validate_action",
]
