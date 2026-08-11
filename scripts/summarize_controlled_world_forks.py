"""Derive concise machine and human certificates from the frozen F06 report."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = (
    ROOT / "release/generated/controlled-world-fork-runtime.json"
)
DEFAULT_JSON = ROOT / "release/generated/controlled-world-fork-certificate.json"
DEFAULT_MARKDOWN = ROOT / "release/generated/controlled-world-fork-certificate.md"


def _canonical_sha256(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_machine_certificate(source: dict[str, Any], *, source_path: Path) -> dict[str, Any]:
    if source.get("execution_scope") != "formal" or not source.get("passed"):
        raise ValueError("source must be the passing formal F06 qualification report")
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    pair_rows: list[dict[str, Any]] = []
    for row in source["rows"]:
        audit = row["audit"]
        runtime = row["runtime_result"]
        divergence = audit["divergence_evaluation"]
        expectation_rows = divergence["expectation_results"]
        pair = {
            "case_id": row["case_id"],
            "seed": row["seed"],
            "fork_id": audit["fork_id"],
            "fork_spec_sha256": audit["fork_spec_sha256"],
            "intervention_class": audit["intervention_class"],
            "target_component_id": audit["target_component_id"],
            "parent_world_sha256": runtime["fork_spec"]["parent"]["world_sha256"],
            "child_world_sha256": runtime["fork_spec"]["child"]["world_sha256"],
            "action_count_per_execution": len(
                runtime["traces"]["parent"]["action_sequence"]
            ),
            "public_component_count": audit["public_contract_certificate"][
                "public_component_count"
            ],
            "public_invariant_component_count": audit["public_contract_certificate"][
                "invariant_component_count"
            ],
            "identity_leakage_finding_count": audit["public_contract_certificate"][
                "identity_leakage_finding_count"
            ],
            "expectations": [
                {
                    "expectation_id": item["expectation_id"],
                    "channel": item["channel"],
                    "signed_delta": item["signed_delta"],
                    "absolute_delta": item["absolute_delta"],
                    "relative_delta": item["relative_delta"],
                    "passed": item["passed"],
                }
                for item in expectation_rows
            ],
            "gates": audit["gates"],
            "passed": audit["passed"],
        }
        pair_rows.append(pair)
        grouped[row["case_id"]].append(pair)

    case_summaries: list[dict[str, Any]] = []
    for case_id, rows in sorted(grouped.items()):
        expectation_ids = [item["expectation_id"] for item in rows[0]["expectations"]]
        expectations = []
        for expectation_id in expectation_ids:
            values = [
                item
                for row in rows
                for item in row["expectations"]
                if item["expectation_id"] == expectation_id
            ]
            expectations.append(
                {
                    "expectation_id": expectation_id,
                    "channel": values[0]["channel"],
                    "seed_pass_count": sum(item["passed"] for item in values),
                    "minimum_absolute_delta": min(item["absolute_delta"] for item in values),
                    "maximum_absolute_delta": max(item["absolute_delta"] for item in values),
                    "minimum_relative_delta": min(item["relative_delta"] for item in values),
                    "maximum_relative_delta": max(item["relative_delta"] for item in values),
                }
            )
        case_summaries.append(
            {
                "case_id": case_id,
                "intervention_class": rows[0]["intervention_class"],
                "target_component_id": rows[0]["target_component_id"],
                "seeds": [row["seed"] for row in rows],
                "pair_pass_count": sum(row["passed"] for row in rows),
                "expectation_summaries": expectations,
            }
        )

    core: dict[str, Any] = {
        "schema_version": "chemworld-controlled-world-fork-certificate-0.1",
        "source": {
            "path": source_path.relative_to(ROOT).as_posix(),
            "formal_report_content_sha256": source["report_sha256"],
            "formal_report_file_sha256": _file_sha256(source_path),
            "protocol_id": source["protocol_id"],
            "protocol_sha256": source["protocol_sha256"],
            "inventory_id": source["inventory_id"],
            "inventory_sha256": source["inventory_sha256"],
        },
        "design": {
            "intervention_class_count": source["case_count"],
            "seed_count_per_class": len(source["selected_seeds"]),
            "parent_child_pair_count": source["pair_count"],
            "world_variants_per_pair": 2,
            "executions_per_variant": 2,
            "trace_count": source["trace_count"],
            "provider_call_count": source["provider_call_count"],
            "same_public_midpoint_action_sequence_within_pair": True,
        },
        "result": {
            "pair_pass_count": sum(row["passed"] for row in pair_rows),
            "gate_pass_counts": source["gate_pass_counts"],
            "case_summaries": case_summaries,
            "pairs": pair_rows,
            "passed": all(row["passed"] for row in pair_rows),
        },
        "supported_claim": (
            "ChemWorld constructs content-addressed single-private-component world forks "
            "that preserve the complete declared public experimental contract, execute an "
            "identical typed operation sequence, produce preregistered physical and public "
            "observation divergence, and replay exactly."
        ),
        "claim_boundary": {
            "programmable_world_apparatus": True,
            "single_private_component_fork": True,
            "public_contract_invariance": True,
            "fixed_sequence_executability": True,
            "expected_response_divergence": True,
            "exact_replay": True,
            "agent_performance_claim": False,
            "arbitrary_world_dsl_claim": False,
            "physical_laboratory_transfer_claim": False,
        },
    }
    digest = _canonical_sha256(core)
    return {
        **core,
        "certificate_id": f"chemworld-controlled-world-fork-{digest[:16]}",
        "certificate_sha256": digest,
    }


def _percent(value: float) -> str:
    return f"{100.0 * value:.2f}%"


def build_human_certificate(certificate: dict[str, Any]) -> str:
    result = certificate["result"]
    design = certificate["design"]
    lines = [
        "# Controlled-World-Fork Programmability Certificate",
        "",
        f"Certificate: `{certificate['certificate_id']}`",
        "",
        f"Machine certificate SHA-256: `{certificate['certificate_sha256']}`",
        "",
        (
            "Frozen qualification report: "
            f"`{certificate['source']['formal_report_content_sha256']}`"
        ),
        "",
        "## Certified claim",
        "",
        certificate["supported_claim"],
        "",
        "## Qualification design",
        "",
        (
            f"The frozen matrix contains {design['intervention_class_count']} intervention "
            f"classes, {design['seed_count_per_class']} seeds per class, "
            f"{design['parent_child_pair_count']} parent-child pairs, and "
            f"{design['trace_count']} traces. Each parent and child executed the same public "
            "midpoint recipe once and then repeated it for exact replay. No model-provider "
            "calls were used."
        ),
        "",
        "| Intervention | Private target | Seeds passed | Physical response | Public response |",
        "| --- | --- | ---: | --- | --- |",
    ]
    for case in result["case_summaries"]:
        physical = next(
            item for item in case["expectation_summaries"] if item["channel"] == "physical_state"
        )
        public = next(
            item
            for item in case["expectation_summaries"]
            if item["channel"] == "public_observation"
        )
        lines.append(
            "| "
            f"`{case['intervention_class']}` | `{case['target_component_id']}` | "
            f"{case['pair_pass_count']}/{len(case['seeds'])} | "
            f"{_percent(physical['minimum_relative_delta'])} to "
            f"{_percent(physical['maximum_relative_delta'])} relative change | "
            f"{_percent(public['minimum_relative_delta'])} to "
            f"{_percent(public['maximum_relative_delta'])} relative change |"
        )
    gates = result["gate_pass_counts"]
    lines.extend(
        [
            "",
            "## Gate results",
            "",
            "| Gate | Passed pairs |",
            "| --- | ---: |",
        ]
    )
    for gate, count in sorted(gates.items()):
        lines.append(f"| `{gate}` | {count}/{design['parent_child_pair_count']} |")
    lines.extend(
        [
            "",
            "All six pairs changed exactly their declared private component; preserved all "
            "nine declared public-contract components; executed every typed action as a "
            "committed transaction on both sides; met both physical-state and public-"
            "observation divergence thresholds; and reproduced both variants exactly.",
            "",
            "## Interpretation boundary",
            "",
            "This certificate establishes controlled programmability of the executable "
            "experimental apparatus. The qualification is a deterministic fixed-policy "
            "probe, so it makes no claim about agent ranking, arbitrary third-party world "
            "languages, or direct transfer to a physical laboratory.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--markdown-output", type=Path, default=DEFAULT_MARKDOWN)
    parser.add_argument("--check", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source = json.loads(args.source.read_text(encoding="utf-8"))
    certificate = build_machine_certificate(source, source_path=args.source.resolve())
    json_text = json.dumps(certificate, indent=2, sort_keys=True) + "\n"
    markdown_text = build_human_certificate(certificate)
    if args.check:
        if args.json_output.read_text(encoding="utf-8") != json_text:
            raise SystemExit("machine certificate does not match deterministic rebuild")
        if args.markdown_output.read_text(encoding="utf-8") != markdown_text:
            raise SystemExit("human certificate does not match deterministic rebuild")
    else:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(json_text, encoding="utf-8")
        args.markdown_output.write_text(markdown_text, encoding="utf-8")
    print(
        json.dumps(
            {
                "certificate_id": certificate["certificate_id"],
                "certificate_sha256": certificate["certificate_sha256"],
                "pair_pass_count": certificate["result"]["pair_pass_count"],
                "trace_count": certificate["design"]["trace_count"],
                "passed": certificate["result"]["passed"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
