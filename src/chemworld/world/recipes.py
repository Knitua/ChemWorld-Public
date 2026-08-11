"""Recipe validation and compilation for experiment-level planning."""

from __future__ import annotations

from typing import Any

import numpy as np

from chemworld.schemas import SchemaValidationResult, validate_action_schema, validate_recipe_schema
from chemworld.world.actions import canonicalize_action
from chemworld.world.operations import MACRO_OPERATIONS


def recipe_to_event_sequence(action: dict[str, Any]) -> list[dict[str, Any]]:
    """Expand terminal recipe parameters into executable reactor operations."""

    normalized = canonicalize_action(action)
    concentration = float(normalized["initial_concentration"])
    volume = 0.025
    amount = float(np.clip(concentration * volume, 0.0005, 0.040))
    target_temperature = float(normalized["temperature"]) + 273.15
    duration = float(normalized["time"]) * 3600.0
    return [
        {"operation": "add_solvent", "volume_L": volume, "solvent": int(normalized["solvent"])},
        {"operation": "add_reagent", "amount_mol": amount},
        {
            "operation": "add_catalyst",
            "catalyst_amount_mol": 0.00020,
            "catalyst": int(normalized["catalyst"]),
        },
        {
            "operation": "heat",
            "target_temperature_K": target_temperature,
            "duration_s": duration,
            "stirring_speed_rpm": float(normalized["stirring_speed"]),
        },
        {"operation": "terminate"},
        {"operation": "measure", "instrument": "final_assay"},
    ]


def compile_recipe(
    recipe: dict[str, Any],
    *,
    expand_macros: bool = True,
    task_info: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Compile a recipe object or recipe-style action into event actions."""

    if "steps" in recipe:
        result = validate_recipe_schema(recipe)
        if not result.valid:
            raise ValueError(f"Invalid recipe: {', '.join(result.errors)}")
        steps = [_canonical_event_action(step) for step in recipe["steps"]]
        return _checked_steps(
            _expand_steps(steps) if expand_macros else steps,
            task_info=task_info,
        )

    if "operation" in recipe:
        result = validate_action_schema(recipe)
        if not result.valid:
            raise ValueError(f"Invalid recipe action: {', '.join(result.errors)}")
        steps = [_canonical_event_action(recipe)]
        return _checked_steps(
            _expand_steps(steps) if expand_macros else steps,
            task_info=task_info,
        )
    return _checked_steps(recipe_to_event_sequence(recipe), task_info=task_info)


def validate_recipe(
    recipe: dict[str, Any],
    task_info: dict[str, Any] | None = None,
    *,
    expand_macros: bool = True,
) -> SchemaValidationResult:
    """Validate a recipe and ensure it can be compiled."""

    if "steps" in recipe:
        schema_result = validate_recipe_schema(recipe)
        if not schema_result.valid:
            return schema_result
    if "operation" in recipe:
        result = validate_action_schema(recipe)
        if not result.valid:
            return result
    try:
        compile_recipe(recipe, expand_macros=expand_macros, task_info=task_info)
    except (KeyError, TypeError, ValueError) as exc:
        return SchemaValidationResult(False, (str(exc),))
    return SchemaValidationResult(True, ())


def expand_macro_action(action: dict[str, Any]) -> list[dict[str, Any]]:
    """Expand a high-level process macro into executable ChemWorld operations."""

    canonical = _canonical_event_action(action)
    operation = str(canonical["operation"])
    if operation not in MACRO_OPERATIONS:
        return [canonical]

    if operation == "wash":
        wash_volume = float(canonical.get("wash_volume_L", 0.010))
        return [
            {
                "operation": "add_phase",
                "phase": "aqueous",
                "volume_L": wash_volume,
            },
            {
                "operation": "mix",
                "duration_s": float(canonical.get("mix_duration_s", 120.0)),
                "stirring_speed_rpm": float(canonical.get("stirring_speed_rpm", 600.0)),
            },
            {
                "operation": "settle",
                "duration_s": float(canonical.get("settle_duration_s", 300.0)),
            },
            {
                "operation": "separate_phase",
                "target_phase": str(canonical.get("target_phase", "organic")),
            },
        ]
    if operation == "dry":
        return [{"operation": "dry"}]
    if operation == "concentrate":
        return [
            {
                "operation": "concentrate",
                "duration_s": float(canonical.get("duration_s", 600.0)),
            }
        ]
    raise ValueError(f"Unsupported macro operation: {operation}")


def _canonical_event_action(action: dict[str, Any]) -> dict[str, Any]:
    from chemworld.action_codec import ActionCodec

    return ActionCodec().canonicalize(dict(action))


def _expand_steps(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    expanded: list[dict[str, Any]] = []
    for step in steps:
        expanded.extend(expand_macro_action(step))
    return expanded


def _checked_steps(
    steps: list[dict[str, Any]],
    *,
    task_info: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    if not steps:
        raise ValueError("Compiled recipe produced no executable steps")
    errors: list[str] = []
    allowed_operations = set(task_info.get("allowed_operations", ())) if task_info else set()
    allowed_instruments = set(task_info.get("allowed_instruments", ())) if task_info else set()
    for index, step in enumerate(steps):
        result = validate_action_schema(step)
        errors.extend(f"compiled_steps[{index}]: {error}" for error in result.errors)
        operation = str(step.get("operation", ""))
        if allowed_operations and operation not in allowed_operations:
            errors.append(f"compiled_steps[{index}]: operation not allowed by task: {operation}")
        if operation == "measure" and allowed_instruments:
            instrument = str(step.get("instrument", "hplc"))
            if instrument not in allowed_instruments:
                errors.append(
                    f"compiled_steps[{index}]: instrument not allowed by task: {instrument}"
                )
    if errors:
        raise ValueError("; ".join(errors))
    return steps


__all__ = [
    "compile_recipe",
    "expand_macro_action",
    "recipe_to_event_sequence",
    "validate_recipe",
]
