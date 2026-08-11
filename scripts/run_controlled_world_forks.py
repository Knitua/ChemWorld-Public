"""Run deterministic controlled-world-fork preflight or qualification matrices."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from chemworld.eval.world_fork_audit import audit_runtime_world_fork
from chemworld.foundation.world_fork_divergence import DivergenceOracleSpec
from chemworld.foundation.world_fork_manifest import load_world_component_inventory
from chemworld.foundation.world_fork_runtime import (
    load_world_fork_qualification_config,
    run_runtime_world_fork,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "configs/benchmark/work_i_world_fork_qualification_v0.1.json"
DEFAULT_OUTPUT = (
    ROOT
    / "release/generated/controlled-world-fork-runtime.json"
)


def _sha256(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def build_report(
    config: dict[str, Any],
    *,
    selected_seeds: tuple[int, ...] | None = None,
) -> dict[str, Any]:
    inventory_path = ROOT / str(config["inventory_path"])
    inventory = load_world_component_inventory(inventory_path)
    configured_seeds = tuple(int(seed) for seed in config["seeds"])
    seeds = configured_seeds if selected_seeds is None else selected_seeds
    if not seeds or not set(seeds).issubset(configured_seeds):
        raise ValueError("selected seeds must be a non-empty subset of configured seeds")
    rows: list[dict[str, Any]] = []
    for case in config["cases"]:
        oracle = DivergenceOracleSpec.from_dict(case["oracle"], inventory=inventory)
        for seed in seeds:
            runtime = run_runtime_world_fork(
                inventory=inventory,
                task_id=str(case["task_id"]),
                seed=seed,
                intervention_class=case["intervention_class"],
                target_component_id=str(case["target_component_id"]),
                intervention_payload=case["intervention_payload"],
                noise_namespace=str(config["noise_contract"]["namespace"]),
            )
            audit = audit_runtime_world_fork(runtime, inventory=inventory, oracle=oracle)
            rows.append(
                {
                    "case_id": case["case_id"],
                    "seed": seed,
                    "runtime_result": runtime,
                    "audit": audit,
                }
            )
    trace_count = len(rows) * 4
    report: dict[str, Any] = {
        "report_version": "chemworld-controlled-world-fork-runtime-0.1",
        "protocol_id": config["protocol_id"],
        "protocol_sha256": _sha256(config),
        "inventory_id": inventory.inventory_id,
        "inventory_sha256": inventory.content_sha256,
        "execution_scope": "formal" if seeds == configured_seeds else "preflight_subset",
        "selected_seeds": list(seeds),
        "case_count": len(config["cases"]),
        "pair_count": len(rows),
        "trace_count": trace_count,
        "provider_call_count": 0,
        "rows": rows,
        "gate_pass_counts": {
            gate: sum(bool(row["audit"]["gates"][gate]) for row in rows)
            for gate in next(iter(rows))["audit"]["gates"]
        },
        "passed": all(row["audit"]["passed"] for row in rows),
        "claim_boundary": {
            "world_fork_runtime_qualified": True,
            "fixed_policy_probe": True,
            "agent_performance_claim": False,
        },
    }
    report["report_sha256"] = _sha256(report)
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--seeds",
        type=str,
        default="0",
        help="comma-separated seed subset, or 'all' for the frozen formal matrix",
    )
    parser.add_argument("--check", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = load_world_fork_qualification_config(args.config)
    selected = (
        None
        if args.seeds == "all"
        else tuple(int(item.strip()) for item in args.seeds.split(",") if item.strip())
    )
    report = build_report(config, selected_seeds=selected)
    if args.check:
        if not args.output.exists():
            raise SystemExit(f"missing report: {args.output}")
        committed = json.loads(args.output.read_text(encoding="utf-8"))
        if committed != report:
            raise SystemExit("committed report does not match deterministic rebuild")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    print(
        json.dumps(
            {
                "output": str(args.output),
                "execution_scope": report["execution_scope"],
                "pair_count": report["pair_count"],
                "trace_count": report["trace_count"],
                "passed": report["passed"],
                "report_sha256": report["report_sha256"],
            },
            sort_keys=True,
        )
    )
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
