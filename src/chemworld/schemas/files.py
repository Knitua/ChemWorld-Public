"""Packaged schema file accessors."""

from __future__ import annotations

import json
from importlib.resources import files
from typing import Any

SCHEMA_FILE_NAMES = {
    "action": "action_schema.json",
    "manifest": "manifest_schema.json",
    "mechanism": "mechanism_schema.json",
    "observation": "observation_schema.json",
    "recipe": "recipe_schema.json",
    "scenario": "scenario_schema.json",
    "task": "task_schema.json",
    "trajectory": "trajectory_schema.json",
}


def load_schema_file(schema_id: str) -> dict[str, Any]:
    try:
        filename = SCHEMA_FILE_NAMES[schema_id]
    except KeyError as exc:
        available = ", ".join(sorted(SCHEMA_FILE_NAMES))
        raise KeyError(f"Unknown schema_id={schema_id!r}. Available: {available}") from exc
    text = files("chemworld.schemas").joinpath(filename).read_text(encoding="utf-8")
    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise ValueError(f"{filename} must contain a JSON object")
    return payload


__all__ = ["SCHEMA_FILE_NAMES", "load_schema_file"]
