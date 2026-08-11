from __future__ import annotations

import json

import pytest
from scripts.build_readme_visuals import (
    DERIVED_OUTPUT,
    MARKDOWN_OUTPUT,
    SITE_DATA_OUTPUT,
    SVG_OUTPUT,
    build_payload,
    render_markdown,
    render_svg,
)


def test_representative_public_visuals_match_frozen_evidence() -> None:
    payload = build_payload()

    assert payload["agent_lifecycle"]["summary"]["committed_actions"] == 15
    assert payload["rollback_recovery"]["summary"]["rolled_back_actions"] == 1
    assert payload["controlled_world_forks"]["summary"] == {
        "all_gates_passed": True,
        "pairs": 6,
        "provider_calls": 0,
        "traces": 24,
    }
    partition_physical = payload["controlled_world_forks"]["pairs"][0]["expectations"][0]
    assert partition_physical["signed_relative_change_percent"] == pytest.approx(21.36267864027609)
    assert json.loads(DERIVED_OUTPUT.read_text(encoding="utf-8")) == payload
    assert json.loads(SITE_DATA_OUTPUT.read_text(encoding="utf-8")) == payload
    assert SVG_OUTPUT.read_text(encoding="utf-8") == render_svg(payload)
    assert MARKDOWN_OUTPUT.read_text(encoding="utf-8") == render_markdown(payload)


def test_public_visuals_exclude_private_reasoning_and_raw_provider_content() -> None:
    joined = "\n".join(
        [
            DERIVED_OUTPUT.read_text(encoding="utf-8"),
            SVG_OUTPUT.read_text(encoding="utf-8"),
            MARKDOWN_OUTPUT.read_text(encoding="utf-8"),
        ]
    ).lower()

    assert "private_reasoning" not in joined
    assert "raw provider" not in joined
    assert "prompt_hash" not in joined
    assert "input_token_count" not in joined
