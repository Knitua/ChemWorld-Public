from __future__ import annotations

import gzip
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "evidence/reports/controlled-world-forks.json.gz"


def _report() -> dict:
    with gzip.open(REPORT, "rt", encoding="utf-8") as handle:
        value = json.load(handle)
    assert isinstance(value, dict)
    return value


def test_world_fork_report_has_complete_success_counts_and_boundaries() -> None:
    report = _report()

    assert report["execution_scope"] == "formal"
    assert report["selected_seeds"] == [0, 1, 2]
    assert report["case_count"] == 2
    assert report["pair_count"] == 6
    assert report["trace_count"] == 24
    assert report["provider_call_count"] == 0
    assert report["passed"] is True
    assert all(value == 6 for value in report["gate_pass_counts"].values())
    assert all(
        row["audit"]["public_contract_certificate"]["public_component_count"] == 9
        and row["audit"]["public_contract_certificate"]["invariant_component_count"] == 9
        and row["audit"]["public_contract_certificate"]["identity_leakage_finding_count"]
        == 0
        for row in report["rows"]
    )
    assert report["claim_boundary"] == {
        "world_fork_runtime_qualified": True,
        "fixed_policy_probe": True,
        "agent_performance_claim": False,
    }
