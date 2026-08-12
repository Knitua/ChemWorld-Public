#!/usr/bin/env python3
"""Build the deterministic manifest for the ChemWorld v0.4.0 public release."""

from __future__ import annotations

import gzip
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "release" / "manifest.json"
OUTPUT_RELATIVE = OUTPUT.relative_to(ROOT).as_posix()
FROZEN_PUBLIC_SNAPSHOT = "9df278371a030de2d6fd582d797931fdf90cd618"
RUNTIME_EVIDENCE_SNAPSHOT = "6729ed6d422f479e687ed8e9a0f9d7b1e35e5261"
PUBLIC_V020_RELEASE = "03e8026301c185fd6ba5bdbda7460765d9b3e724"
REPORT_NAMES = (
    "composition-qualification.json.gz",
    "deterministic-use-cases.json.gz",
    "controlled-world-forks.json.gz",
    "agent-instrument-use.json.gz",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tracked_files() -> list[str]:
    completed = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    paths = [item.decode("utf-8") for item in completed.stdout.split(b"\0") if item]
    if paths != sorted(paths):
        paths.sort()
    return paths


def read_report(name: str) -> dict[str, Any]:
    with gzip.open(ROOT / "evidence" / "reports" / name, "rt", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise RuntimeError(f"JSON object required: {name}")
    return value


def main() -> int:
    paths = tracked_files()
    if OUTPUT_RELATIVE not in paths:
        raise RuntimeError(f"manifest must already be tracked: {OUTPUT_RELATIVE}")
    bound_paths = [path for path in paths if path != OUTPUT_RELATIVE]
    files = []
    for relative in bound_paths:
        path = ROOT / relative
        if not path.is_file():
            raise RuntimeError(f"tracked release file is missing: {relative}")
        files.append(
            {
                "path": relative,
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
        )

    sanitization_receipts = {}
    for name in REPORT_NAMES:
        receipt = read_report(name).get("release_sanitization")
        if not isinstance(receipt, dict):
            raise RuntimeError(f"sanitization receipt is missing: {name}")
        sanitization_receipts[f"evidence/reports/{name}"] = receipt

    payload = {
        "schema_version": "chemworld-stable-software-evidence-release-0.4",
        "status": "stable_software_evidence_release",
        "release_version": "0.4.0",
        "release_date": "2026-08-12",
        "repository": "https://github.com/sunyrain/ChemWorld-Public",
        "provenance": {
            "frozen_public_snapshot": FROZEN_PUBLIC_SNAPSHOT,
            "runtime_and_evidence_snapshot": RUNTIME_EVIDENCE_SNAPSHOT,
            "presentation_and_tutorial_base": PUBLIC_V020_RELEASE,
            "construction": (
                "provider-free Student Lab added to the stable public runtime"
            ),
            "scope": (
                "stable_runtime_evidence_docs_tutorials_agent_onboarding_and_student_lab"
            ),
        },
        "headline_denominators": {
            "reference_task_world_units": [64, 64],
            "reference_recipes": [1786, 1786],
            "generated_compositions": [52, 52],
            "non_reference_distillation_compositions": [8, 8],
            "module_probes": [32, 32],
            "interface_paths": [7, 7],
            "invalid_declarations": [7, 7],
            "invalid_action_probes": [192, 192],
            "deterministic_use_cases": [8, 8],
            "submitted_deterministic_actions": [89, 89],
            "controlled_world_fork_pairs": [6, 6],
            "controlled_world_fork_traces": [24, 24],
            "independent_agent_lifecycles": [1, 1],
            "independent_agent_actions": [15, 15],
        },
        "sanitization_receipts": sanitization_receipts,
        "excluded": [
            "manuscript text, PDFs, manuscript figures and source packages",
            "planning, TODO, workstream, draft, interim and pilot material",
            "raw provider responses, private reasoning and provider session identifiers",
            "private evaluator configuration, credentials, caches and local run directories",
            "unpublished experiment matrices and all post-freeze development artifacts",
        ],
        "manifest_self_exclusion": {
            "path": OUTPUT_RELATIVE,
            "reason": "the manifest cannot hash itself without circularity",
        },
        "files": files,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": payload["status"], "file_count": len(files)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
