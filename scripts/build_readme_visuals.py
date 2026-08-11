#!/usr/bin/env python3
# ruff: noqa: E501
"""Build reader-facing trajectory and controlled-world visualizations from frozen evidence."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import html
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPORT_ROOT = ROOT / "evidence" / "reports"
AGENT_REPORT = REPORT_ROOT / "agent-instrument-use.json.gz"
DETERMINISTIC_REPORT = REPORT_ROOT / "deterministic-use-cases.json.gz"
FORK_REPORT = REPORT_ROOT / "controlled-world-forks.json.gz"
DERIVED_OUTPUT = ROOT / "evidence" / "derived" / "representative-behavior-and-forks.json"
SVG_OUTPUT = ROOT / "docs" / "assets" / "representative-agent-and-world-change.svg"
SITE_DATA_OUTPUT = ROOT / "docs" / "assets" / "data" / "representative-behavior-and-forks.json"
MARKDOWN_OUTPUT = ROOT / "docs" / "representative-behavior.md"
GENERATOR_VERSION = "chemworld-public-readme-visuals-0.1"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_gzip_json(path: Path) -> dict[str, Any]:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise RuntimeError(f"JSON object required: {path}")
    return value


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _action_label(action: dict[str, Any]) -> str:
    operation = str(action["operation"])
    if operation == "measure":
        instrument = str(action.get("instrument", "instrument"))
        return "Final assay" if instrument == "final_assay" else instrument.upper()
    replacements = {
        "add_reagent": "Reagent",
        "add_solvent": "Solvent",
        "add_catalyst": "Catalyst",
        "collect_fraction": "Fraction",
        "separate_phase": "Separate",
        "add_phase": "Add phase",
        "add_extractant": "Extractant",
    }
    return replacements.get(operation, operation.replace("_", " ").title())


def _action_details(action: dict[str, Any]) -> str:
    operation = str(action["operation"])
    if operation == "add_reagent":
        return f"{action['amount_mol']:g} mol"
    if operation == "add_solvent":
        return f"{action['volume_L']:g} L; solvent {action['solvent']}"
    if operation == "add_catalyst":
        return f"{action['catalyst_amount_mol']:g} mol; catalyst {action['catalyst']}"
    if operation in {"heat", "evaporate", "distill"}:
        parts = [f"{action['target_temperature_K']:g} K", f"{action['duration_s']:g} s"]
        if "reflux_ratio" in action:
            parts.append(f"reflux {action['reflux_ratio']:g}")
        return "; ".join(parts)
    if operation in {"wait", "mix", "settle", "concentrate"}:
        return f"{action['duration_s']:g} s"
    if operation == "measure":
        return str(action["instrument"])
    if operation == "collect_fraction" or operation == "transfer":
        return f"fraction {action['transfer_fraction']:g}"
    if operation == "add_phase":
        return f"{action['volume_L']:g} L; {action['phase']}"
    if operation == "add_extractant":
        return f"{action['volume_L']:g} L; extractant {action['extractant']}"
    if operation == "separate_phase":
        return str(action["target_phase"])
    if operation == "wash":
        return f"{action['wash_volume_L']:g} L"
    return "—"


def _observation_highlight(observation: dict[str, Any], action: dict[str, Any]) -> str:
    if action["operation"] != "measure":
        return "—"
    candidates = [
        ("conversion", "conversion"),
        ("yield", "yield"),
        ("purity", "purity"),
        ("distillate_purity", "distillate purity"),
        ("distillate_recovery", "distillate recovery"),
        ("score", "endpoint score" if action.get("instrument") == "final_assay" else "score"),
    ]
    values = []
    for key, label in candidates:
        value = _finite_number(observation.get(key))
        if value is not None:
            values.append(f"{label} {value:.3f}")
    return "; ".join(values[:5]) or "structured observation packet"


def _agent_payload(report: dict[str, Any]) -> dict[str, Any]:
    summary = report["summary"]
    if report.get("status") != "passed" or summary.get("submitted_action_count") != 15:
        raise RuntimeError("agent evidence is not the frozen passing 15-action lifecycle")
    cumulative_time = 0.0
    actions = []
    for row in report["actions"]:
        transaction = row["transaction"]
        if transaction.get("status") != "committed":
            raise RuntimeError("representative agent lifecycle contains a non-committed action")
        resource_delta = row["resource_outcome_delta"]
        report_only = resource_delta["report_only"]
        time_delta = float(report_only["process_time_s"])
        cumulative_time += time_delta
        observation = row["public_observation"]
        actions.append(
            {
                "step": int(row["step"]),
                "action": row["action"],
                "label": _action_label(row["action"]),
                "details": _action_details(row["action"]),
                "transaction_status": transaction["status"],
                "process_time_delta_s": time_delta,
                "cumulative_process_time_s": cumulative_time,
                "physical_cost_delta": float(report_only["physical_cost"]),
                "sample_consumed_delta_L": float(report_only["sample_consumed_L"]),
                "public_score": _finite_number(observation.get("score")),
                "observation_highlight": _observation_highlight(observation, row["action"]),
                "terminated": bool(row["terminated"]),
            }
        )
    final = report["lifecycle"]["evaluation_receipt"]["public_observation"]
    return {
        "title": "Persistent agent in a non-reference reaction-distillation world",
        "summary": {
            "submitted_actions": int(summary["submitted_action_count"]),
            "committed_actions": int(summary["committed_action_count"]),
            "provider_sessions": int(summary["provider_session_count"]),
            "rollbacks": int(summary["rollback_count"]),
            "process_time_used_s": cumulative_time,
            "process_time_limit_s": float(
                report["declared_resource_budget"]["declared_limits"]["process_time_s"]
            ),
            "exact_replay": bool(report["exact_replay"]["verified"]),
            "public_private_leakage_count": int(summary["public_private_leakage_count"]),
        },
        "final_public_observation": {
            key: float(final[key])
            for key in (
                "conversion",
                "yield",
                "selectivity",
                "distillate_purity",
                "distillate_recovery",
                "score",
            )
        },
        "actions": actions,
    }


def _recovery_payload(report: dict[str, Any]) -> dict[str, Any]:
    case = next(item for item in report["cases"] if item["case_id"] == "U03/E01")
    if not case.get("passed") or case.get("rollback_count") != 1:
        raise RuntimeError("U03/E01 is not the frozen passing single-rollback case")
    receipts = case["step_receipts"]
    if len(receipts) != 19 or receipts[0]["transaction_status"] != "rolled_back":
        raise RuntimeError("U03/E01 action census changed")
    actions = []
    for receipt in receipts:
        resource_delta = receipt["resource_outcome_delta"]["report_only"]
        actions.append(
            {
                "step": int(receipt["step"]),
                "action": receipt["action"],
                "label": _action_label(receipt["action"]),
                "details": _action_details(receipt["action"]),
                "transaction_status": receipt["transaction_status"],
                "rollback_reason": receipt["rollback_reason"],
                "process_time_delta_s": float(resource_delta["process_time_s"]),
                "terminated": bool(receipt["terminated"]),
            }
        )
    rollback = case["recovery_receipt"]["rollback_recovery_receipt"]
    penalty = rollback["ledger"]["declared_failure_penalty"]
    return {
        "title": "Planned precondition failure followed by recovery",
        "summary": {
            "submitted_actions": int(case["submitted_action_count"]),
            "committed_actions": int(case["committed_action_count"]),
            "rolled_back_actions": int(case["rolled_back_action_count"]),
            "final_assays": int(case["committed_final_assay_count"]),
            "exact_replay": bool(case["exact_replay"]["verified"]),
            "physical_state_preserved_on_rollback": bool(rollback["physical"]["preserved"]),
            "observation_rng_preserved_on_rollback": bool(rollback["observation_rng"]["preserved"]),
            "ghost_state_preserved_on_rollback": bool(rollback["ghost_state_preserved"]),
            "rollback_penalty": {
                "cost": float(penalty["cost"]),
                "risk": float(penalty["risk"]),
                "sample_consumed_L": float(penalty["sample_consumed_L"]),
                "time_s": float(penalty["time_s"]),
            },
        },
        "actions": actions,
    }


def _fork_payload(report: dict[str, Any]) -> dict[str, Any]:
    if not report.get("passed") or report.get("pair_count") != 6:
        raise RuntimeError("controlled-world evidence is not the frozen passing six-pair matrix")
    rows = []
    for row in report["rows"]:
        audit = row["audit"]
        expectations = []
        for item in audit["divergence_evaluation"]["expectation_results"]:
            parent = float(item["parent_value"])
            signed_delta = float(item["signed_delta"])
            relative_change_percent = 100.0 * float(item["relative_delta"])
            signed_percent = (
                relative_change_percent if signed_delta >= 0.0 else -relative_change_percent
            )
            expectations.append(
                {
                    "channel": item["channel"],
                    "expectation_id": item["expectation_id"],
                    "parent_value": parent,
                    "child_value": float(item["child_value"]),
                    "signed_delta": signed_delta,
                    "relative_change_percent": relative_change_percent,
                    "signed_relative_change_percent": signed_percent,
                    "passed": bool(item["passed"]),
                }
            )
        rows.append(
            {
                "case_id": row["case_id"],
                "seed": int(row["seed"]),
                "intervention_class": audit["intervention_class"],
                "target_component_id": audit["target_component_id"],
                "public_contract_invariant": bool(audit["gates"]["public_contract_invariance"]),
                "same_sequence_executable": bool(audit["gates"]["same_sequence_executability"]),
                "exact_replay": bool(audit["gates"]["exact_replay"]),
                "expectations": expectations,
            }
        )
    return {
        "title": "Single-private-law controlled world forks",
        "summary": {
            "pairs": int(report["pair_count"]),
            "traces": int(report["trace_count"]),
            "provider_calls": int(report["provider_call_count"]),
            "all_gates_passed": all(
                value == report["pair_count"] for value in report["gate_pass_counts"].values()
            ),
        },
        "pairs": rows,
    }


def build_payload() -> dict[str, Any]:
    return {
        "schema_version": GENERATOR_VERSION,
        "sources": {
            path.name: {"path": path.relative_to(ROOT).as_posix(), "sha256": _sha256(path)}
            for path in (AGENT_REPORT, DETERMINISTIC_REPORT, FORK_REPORT)
        },
        "agent_lifecycle": _agent_payload(_read_gzip_json(AGENT_REPORT)),
        "rollback_recovery": _recovery_payload(_read_gzip_json(DETERMINISTIC_REPORT)),
        "controlled_world_forks": _fork_payload(_read_gzip_json(FORK_REPORT)),
        "claim_boundary": [
            "These are representative views of frozen qualification evidence, not new experiments.",
            "The agent lifecycle is an interface-integration demonstration, not a model ranking.",
            "Controlled forks qualify registered single-private-component interventions within the declared software-model domain.",
        ],
    }


def _svg_text(x: float, y: float, value: str, css_class: str, anchor: str = "start") -> str:
    return (
        f'<text x="{x:g}" y="{y:g}" class="{css_class}" text-anchor="{anchor}">'
        f"{html.escape(value)}</text>"
    )


def _operation_color(operation: str, instrument: str | None = None) -> str:
    if operation == "measure":
        return "#16A34A" if instrument == "final_assay" else "#7C3AED"
    if operation in {"add_reagent", "add_solvent", "add_catalyst", "add_phase", "add_extractant"}:
        return "#2563EB"
    if operation in {"heat", "wait", "quench"}:
        return "#EA580C"
    if operation in {
        "evaporate",
        "distill",
        "collect_fraction",
        "separate_phase",
        "wash",
        "dry",
        "concentrate",
        "transfer",
        "mix",
        "settle",
    }:
        return "#0F766E"
    return "#475569"


def render_svg(payload: dict[str, Any]) -> str:
    agent = payload["agent_lifecycle"]
    recovery = payload["rollback_recovery"]
    forks = payload["controlled_world_forks"]
    width, height = 1600, 1090
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">',
        '<title id="title">Representative ChemWorld agent behavior and controlled world changes</title>',
        '<desc id="desc">Three panels show a fifteen-action agent lifecycle, a rollback and recovery trajectory, and response changes under single-private-law world forks.</desc>',
        """<style>
        .title{font:700 34px Inter,Segoe UI,Arial,sans-serif;fill:#0F172A}
        .subtitle{font:400 18px Inter,Segoe UI,Arial,sans-serif;fill:#475569}
        .panel-title{font:700 23px Inter,Segoe UI,Arial,sans-serif;fill:#0F172A}
        .panel-note{font:400 15px Inter,Segoe UI,Arial,sans-serif;fill:#475569}
        .small{font:500 13px Inter,Segoe UI,Arial,sans-serif;fill:#334155}
        .tiny{font:600 11px Inter,Segoe UI,Arial,sans-serif;fill:#334155}
        .white{font:700 11px Inter,Segoe UI,Arial,sans-serif;fill:#FFFFFF}
        .metric{font:700 15px Inter,Segoe UI,Arial,sans-serif;fill:#0F172A}
        .axis{stroke:#CBD5E1;stroke-width:1}
        .zero{stroke:#64748B;stroke-width:2;stroke-dasharray:5 5}
        </style>""",
        f'<rect width="{width}" height="{height}" fill="#F8FAFC"/>',
        _svg_text(54, 54, "ChemWorld in action", "title"),
        _svg_text(
            54,
            82,
            "Frozen trajectories expose decisions, transactions, observations, resources and controlled world changes.",
            "subtitle",
        ),
    ]

    def panel(x: int, y: int, w: int, h: int) -> None:
        parts.append(
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="22" fill="#FFFFFF" stroke="#E2E8F0" stroke-width="2"/>'
        )

    panel(42, 105, 1516, 390)
    parts.extend(
        [
            _svg_text(
                70,
                143,
                "A  One persistent agent closes a complete experimental lifecycle",
                "panel-title",
            ),
            _svg_text(
                70,
                169,
                "Fifteen operation-level decisions in a coverage-generated reaction-distillation world; all transactions committed.",
                "panel-note",
            ),
        ]
    )
    timeline_x, timeline_y, cell_w, gap = 70, 195, 91, 7
    for index, row in enumerate(agent["actions"]):
        x = timeline_x + index * (cell_w + gap)
        action = row["action"]
        color = _operation_color(str(action["operation"]), action.get("instrument"))
        parts.append(
            f'<rect x="{x}" y="{timeline_y}" width="{cell_w}" height="58" rx="10" fill="{color}"/>'
        )
        parts.append(_svg_text(x + 10, timeline_y + 19, str(row["step"]), "white"))
        label = str(row["label"])
        if len(label) > 12:
            label = label[:11] + "…"
        parts.append(_svg_text(x + cell_w / 2, timeline_y + 43, label, "white", "middle"))

    chart_x, chart_y, chart_w, chart_h = 95, 300, 1050, 125
    parts.append(
        _svg_text(
            70,
            284,
            "Public score after each committed action (descriptive endpoint signal)",
            "small",
        )
    )
    for fraction in (0.0, 0.1, 0.2, 0.3):
        y = chart_y + chart_h - (fraction / 0.3) * chart_h
        parts.append(
            f'<line x1="{chart_x}" y1="{y:g}" x2="{chart_x + chart_w}" y2="{y:g}" class="axis"/>'
        )
        parts.append(_svg_text(chart_x - 12, y + 4, f"{fraction:.1f}", "tiny", "end"))
    points = []
    for index, row in enumerate(agent["actions"]):
        score = float(row["public_score"] or 0.0)
        x = chart_x + index * chart_w / 14
        y = chart_y + chart_h - min(score, 0.3) / 0.3 * chart_h
        points.append((x, y, row))
    parts.append(
        '<polyline fill="none" stroke="#2563EB" stroke-width="4" points="'
        + " ".join(f"{x:.1f},{y:.1f}" for x, y, _ in points)
        + '"/>'
    )
    for x, y, row in points:
        instrument = row["action"].get("instrument")
        radius = 7 if instrument else 4
        color = _operation_color(str(row["action"]["operation"]), instrument)
        parts.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{radius}" fill="{color}" stroke="#FFFFFF" stroke-width="2"/>'
        )
    summary = agent["summary"]
    callout_x = 1190
    callouts = [
        ("15 / 15", "actions committed"),
        (
            f"{summary['process_time_used_s']:.1f} / {summary['process_time_limit_s']:.0f} s",
            "process-time ledger",
        ),
        ("2 HPLC + 1 GC", "process measurements"),
        ("exact", "submitted-trace replay"),
        (f"{agent['final_public_observation']['score']:.3f}", "final descriptive score"),
    ]
    for idx, (value, label) in enumerate(callouts):
        y = 296 + idx * 34
        parts.append(_svg_text(callout_x, y, value, "metric"))
        parts.append(_svg_text(callout_x + 155, y, label, "small"))

    panel(42, 515, 1516, 230)
    parts.extend(
        [
            _svg_text(
                70,
                553,
                "B  A rejected operation remains part of the scientific record",
                "panel-title",
            ),
            _svg_text(
                70,
                579,
                "The first action violates runtime preconditions, rolls back physical state, and is followed by eighteen valid recovery actions.",
                "panel-note",
            ),
        ]
    )
    start_x, y, spacing = 78, 625, 76
    for index, row in enumerate(recovery["actions"]):
        x = start_x + index * spacing
        rolled_back = row["transaction_status"] == "rolled_back"
        fill = "#DC2626" if rolled_back else "#16A34A"
        parts.append(f'<circle cx="{x}" cy="{y}" r="17" fill="{fill}"/>')
        parts.append(_svg_text(x, y + 4, str(row["step"]), "white", "middle"))
        if index < len(recovery["actions"]) - 1:
            parts.append(
                f'<line x1="{x + 18}" y1="{y}" x2="{x + spacing - 18}" y2="{y}" stroke="#CBD5E1" stroke-width="3"/>'
            )
    key_labels = {
        1: "rollback",
        2: "setup",
        5: "reaction",
        7: "HPLC",
        12: "separate",
        17: "HPLC",
        18: "terminate",
        19: "final assay",
    }
    for step, label in key_labels.items():
        x = start_x + (step - 1) * spacing
        parts.append(_svg_text(x, y + 37, label, "tiny", "middle"))
    penalty = recovery["summary"]["rollback_penalty"]
    parts.append(
        _svg_text(
            78,
            712,
            f"Rollback consequence: physical state, observation RNG and ghost state preserved; declared attempt cost +{penalty['cost']:.2f}, risk +{penalty['risk']:.2f}.",
            "small",
        )
    )

    panel(42, 765, 1516, 295)
    parts.extend(
        [
            _svg_text(
                70,
                803,
                "C  Change one private law while holding the public experiment fixed",
                "panel-title",
            ),
            _svg_text(
                70,
                829,
                "Six parent-child pairs use the same public contract and typed action sequence; dots show registered signed relative changes across three seeds.",
                "panel-note",
            ),
        ]
    )
    plot_x, plot_y, plot_w = 620, 858, 850
    minimum, maximum = -25.0, 25.0

    def x_scale(value: float) -> float:
        return plot_x + (value - minimum) / (maximum - minimum) * plot_w

    zero_x = x_scale(0.0)
    parts.append(f'<line x1="{zero_x:.1f}" y1="850" x2="{zero_x:.1f}" y2="978" class="zero"/>')
    for tick in (-20, -10, 0, 10, 20):
        x = x_scale(float(tick))
        parts.append(f'<line x1="{x:.1f}" y1="972" x2="{x:.1f}" y2="979" stroke="#64748B"/>')
        parts.append(_svg_text(x, 997, f"{tick:+d}%", "tiny", "middle"))
    row_specs = [
        (
            "partition-constitutive-law-family",
            "physical_state",
            "Partition: physical amount",
            "#16A34A",
        ),
        (
            "partition-constitutive-law-family",
            "public_observation",
            "Partition: public product fraction",
            "#15803D",
        ),
        (
            "electrochemical-material-law-counterfactual",
            "physical_state",
            "Electrochemical: physical amount",
            "#F97316",
        ),
        (
            "electrochemical-material-law-counterfactual",
            "public_observation",
            "Electrochemical: public ohmic efficiency",
            "#DC2626",
        ),
    ]
    for row_index, (case_id, channel, label, color) in enumerate(row_specs):
        y = plot_y + row_index * 34
        values = [
            expectation["signed_relative_change_percent"]
            for pair in forks["pairs"]
            if pair["case_id"] == case_id
            for expectation in pair["expectations"]
            if expectation["channel"] == channel
        ]
        parts.append(_svg_text(78, y + 5, label, "small"))
        x1, x2 = x_scale(min(values)), x_scale(max(values))
        parts.append(
            f'<line x1="{x1:.1f}" y1="{y}" x2="{x2:.1f}" y2="{y}" stroke="{color}" stroke-width="7" stroke-linecap="round" opacity="0.45"/>'
        )
        for value in values:
            parts.append(
                f'<circle cx="{x_scale(value):.1f}" cy="{y}" r="7" fill="{color}" stroke="#FFFFFF" stroke-width="2"/>'
            )
        parts.append(
            _svg_text(1490, y + 5, f"{min(values):+.1f}% to {max(values):+.1f}%", "small", "end")
        )
    parts.append(
        _svg_text(
            70,
            1040,
            "All 6 pairs passed single-target lineage, public-contract invariance, same-sequence execution, expected divergence and exact replay.",
            "small",
        )
    )
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def render_markdown(payload: dict[str, Any]) -> str:
    agent = payload["agent_lifecycle"]
    recovery = payload["rollback_recovery"]
    forks = payload["controlled_world_forks"]
    lines = [
        "# Representative agent behavior and controlled world changes",
        "",
        "This page is generated from the frozen public evidence reports. It introduces no new",
        "experiment and does not expose private world state or provider response content.",
        "",
        "![Representative ChemWorld agent behavior and controlled world changes](assets/representative-agent-and-world-change.svg)",
        "",
        "## Persistent agent lifecycle",
        "",
        (
            f"One persistent agent session submitted and committed {agent['summary']['committed_actions']} "
            f"typed actions in a non-reference reaction-distillation world. It used "
            f"{agent['summary']['process_time_used_s']:.3f} of "
            f"{agent['summary']['process_time_limit_s']:.0f} available process seconds, explicitly "
            "terminated, performed one final assay and replayed exactly."
        ),
        "",
        "| Step | Action | Public parameters | Δ process time | Observation highlight |",
        "| ---: | --- | --- | ---: | --- |",
    ]
    for row in agent["actions"]:
        lines.append(
            f"| {row['step']} | `{row['label']}` | {row['details']} | "
            f"{row['process_time_delta_s']:.3f} s | {row['observation_highlight']} |"
        )
    final = agent["final_public_observation"]
    lines.extend(
        [
            "",
            (
                "The final public packet reported "
                f"conversion {final['conversion']:.3f}, yield {final['yield']:.3f}, "
                f"selectivity {final['selectivity']:.3f}, distillate purity "
                f"{final['distillate_purity']:.3f}, distillate recovery "
                f"{final['distillate_recovery']:.3f} and descriptive score "
                f"{final['score']:.3f}."
            ),
            "",
            "## Transaction rollback and recovery",
            "",
            (
                "The deterministic U03/E01 case deliberately attempted `separate_phase` before "
                "material, volume and a settled phase system existed. The transaction rolled "
                "back, preserved physical state, observation RNG and ghost state, retained the "
                "declared attempt consequence, and continued from the last committed state."
            ),
            "",
            "| Step | Action | Transaction | Δ process time | Role in recovery |",
            "| ---: | --- | --- | ---: | --- |",
        ]
    )
    for row in recovery["actions"]:
        if row["step"] == 1:
            role = "Premature separation; rolled back"
        elif row["step"] == 19:
            role = "Final assay closes the recovered lifecycle"
        elif row["step"] == 18:
            role = "Explicit termination"
        elif row["action"]["operation"] == "measure":
            role = "Process measurement"
        else:
            role = "Committed recovery action"
        lines.append(
            f"| {row['step']} | `{row['label']}` | `{row['transaction_status']}` | "
            f"{row['process_time_delta_s']:.3f} s | {role} |"
        )
    penalty = recovery["summary"]["rollback_penalty"]
    lines.extend(
        [
            "",
            (
                f"The rejected attempt retained cost {penalty['cost']:.2f} and risk "
                f"{penalty['risk']:.2f}, while consuming no sample and no process time. The full "
                "19-step submitted trace, including the rollback, replayed exactly."
            ),
            "",
            "## Controlled private-law changes",
            "",
            (
                "For each parent-child pair, ChemWorld held the public task, action schema, "
                "instrument surface, resources and typed action sequence fixed while changing "
                "one registered private component. Signed relative change follows the frozen "
                "qualification evaluator: sign(child-parent) * |child-parent| divided by the "
                "maximum of |parent|, |child| and the registered floor."
            ),
            "",
            "| Intervention | Seed | Private target | Physical response | Public response | Fixed gates |",
            "| --- | ---: | --- | ---: | ---: | --- |",
        ]
    )
    case_labels = {
        "partition-constitutive-law-family": "Partition constitutive law",
        "electrochemical-material-law-counterfactual": "Electrochemical material law",
    }
    for pair in forks["pairs"]:
        physical = next(
            item for item in pair["expectations"] if item["channel"] == "physical_state"
        )
        public = next(
            item for item in pair["expectations"] if item["channel"] == "public_observation"
        )
        lines.append(
            f"| {case_labels[pair['case_id']]} | {pair['seed']} | "
            f"`{pair['target_component_id']}` | "
            f"{physical['signed_relative_change_percent']:+.2f}% | "
            f"{public['signed_relative_change_percent']:+.2f}% | "
            "public contract, sequence, replay |"
        )
    lines.extend(
        [
            "",
            "## Interpretation boundary",
            "",
            "- The agent trajectory demonstrates interface use and auditable execution, not model superiority.",
            "- The rollback case demonstrates transaction and recovery semantics, not a favorable-error selection.",
            "- The fork matrix establishes controlled changes for registered private-law interventions within the declared software-model domain; it does not imply physical-laboratory transfer.",
            "",
            "Machine-readable values and exact source hashes are available in",
            "[`representative-behavior-and-forks.json`](assets/data/representative-behavior-and-forks.json).",
            "",
        ]
    )
    return "\n".join(lines)


def _write_or_check(path: Path, content: str, *, check: bool) -> None:
    if check:
        if not path.is_file() or path.read_text(encoding="utf-8") != content:
            raise RuntimeError(f"generated file is stale: {path.relative_to(ROOT)}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(content)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    payload = build_payload()
    json_text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    _write_or_check(DERIVED_OUTPUT, json_text, check=args.check)
    _write_or_check(SITE_DATA_OUTPUT, json_text, check=args.check)
    _write_or_check(SVG_OUTPUT, render_svg(payload), check=args.check)
    _write_or_check(MARKDOWN_OUTPUT, render_markdown(payload), check=args.check)
    print(
        json.dumps(
            {
                "status": "checked" if args.check else "written",
                "agent_actions": len(payload["agent_lifecycle"]["actions"]),
                "recovery_actions": len(payload["rollback_recovery"]["actions"]),
                "controlled_fork_pairs": len(payload["controlled_world_forks"]["pairs"]),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
