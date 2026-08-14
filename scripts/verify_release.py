#!/usr/bin/env python3
# ruff: noqa: E501
"""Fail-closed offline verification for the ChemWorld v0.4.0 release."""

from __future__ import annotations

import gzip
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "release" / "manifest.json"
MANIFEST_RELATIVE = MANIFEST.relative_to(ROOT).as_posix()
EXPECTED_SANITIZER = "chemworld-public-evidence-sanitizer-1.0"
EXPECTED_SOURCE_REPORTS = {
    "composition-qualification.json.gz": "1fd037b0b3437e025bf6ce05763f471266906c39808b028dbeb36e2a7c28e761",
    "deterministic-use-cases.json.gz": "b906dd3ef56b90a53abdf1dff42e6249d876127eba159a40db06785a86e9ee5e",
    "controlled-world-forks.json.gz": "b95631190d92b2edab319ed50b7e26bccd6bc346eef66ec34c5f60750a80cfd6",
    "agent-instrument-use.json.gz": "fc828231d6b09b8a163d2a286190e68c076707891d0a664cf15989a54441546a",
}

_INTERNAL_WORKSTREAM = "workstreams" + "/arxiv_v1"
_INTERNAL_TODO = "FIRST_PAPER" + "_TODOLIST"
_SERVER_PATH = re.compile(r"/(?:root|home|mnt)/(?:[^\s\"']+)", re.IGNORECASE)
_CREDENTIAL = re.compile(
    r"(?:^|[^A-Za-z0-9])sk-[A-Za-z0-9_-]{16,}|"
    r"gh[pousr]_[A-Za-z0-9]{20,}|"
    r"AKIA[0-9A-Z]{16}|"
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    re.IGNORECASE,
)
TUTORIAL_NOTEBOOKS = (
    "01_first_experiment.ipynb",
    "02_reaction_to_purification.ipynb",
    "03_controlled_world_change.ipynb",
)
_TUTORIAL_FORBIDDEN = re.compile(
    r"private-eval|work\s*ii|"
    + re.escape(_INTERNAL_WORKSTREAM)
    + "|"
    + re.escape(_INTERNAL_TODO)
    + r"|/(?:root|home|mnt)/(?:[^\s\"']+)|"
    + r"(?:sk-|gh[pousr]_)[A-Za-z0-9_-]{16,}",
    re.IGNORECASE,
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def git_output(*args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout


def tracked_files() -> list[str]:
    return sorted(path for path in git_output("ls-files").splitlines() if path)


def read_gzip_json(name: str) -> dict[str, Any]:
    path = ROOT / "evidence" / "reports" / name
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise RuntimeError(f"JSON object required: {path}")
    return value


def verify_manifest(manifest: dict[str, Any]) -> None:
    require(
        manifest.get("status") == "stable_software_evidence_release",
        "release status is not stable_software_evidence_release",
    )
    require(manifest.get("release_version") == "0.4.0", "release version is not 0.4.0")
    self_exclusion = manifest.get("manifest_self_exclusion")
    require(
        isinstance(self_exclusion, dict) and self_exclusion.get("path") == MANIFEST_RELATIVE,
        "manifest self-exclusion is missing or invalid",
    )

    rows = manifest.get("files")
    require(isinstance(rows, list), "manifest files must be a list")
    row_paths = [row.get("path") for row in rows if isinstance(row, dict)]
    require(len(row_paths) == len(rows), "manifest contains a non-object file row")
    require(len(row_paths) == len(set(row_paths)), "manifest contains duplicate file paths")
    require(row_paths == sorted(row_paths), "manifest file paths are not sorted")
    expected_paths = [path for path in tracked_files() if path != MANIFEST_RELATIVE]
    require(row_paths == expected_paths, "manifest and Git tracked-file sets differ")

    for row in rows:
        path = ROOT / row["path"]
        require(path.is_file(), f"missing release file: {row['path']}")
        require(path.stat().st_size == row.get("bytes"), f"byte mismatch: {row['path']}")
        require(sha256(path) == row.get("sha256"), f"hash mismatch: {row['path']}")


def verify_sanitization(name: str, report: dict[str, Any]) -> None:
    receipt = report.get("release_sanitization")
    require(isinstance(receipt, dict), f"sanitization receipt missing: {name}")
    require(
        receipt.get("sanitizer_version") == EXPECTED_SANITIZER,
        f"sanitizer version changed: {name}",
    )
    source = receipt.get("source_report")
    require(isinstance(source, dict), f"source-report receipt missing: {name}")
    require(
        source.get("compressed_sha256") == EXPECTED_SOURCE_REPORTS[name],
        f"original report hash changed: {name}",
    )
    removed = receipt.get("removed_metadata")
    require(isinstance(removed, dict), f"removed-metadata receipt missing: {name}")
    require(isinstance(removed.get("entry_count"), int), f"removed count missing: {name}")
    require(
        isinstance(removed.get("summary_sha256"), str)
        and len(removed["summary_sha256"]) == 64,
        f"removed metadata digest missing: {name}",
    )
    protocol = receipt.get("public_protocol")
    require(isinstance(protocol, dict), f"public protocol receipt missing: {name}")
    protocol_path = ROOT / str(protocol.get("path", ""))
    require(protocol_path.is_file(), f"public protocol missing: {name}")
    require(sha256(protocol_path) == protocol.get("sha256"), f"protocol hash changed: {name}")
    serialization = receipt.get("serialization")
    require(
        isinstance(serialization, dict) and serialization.get("gzip_mtime") == 0,
        f"non-deterministic gzip receipt: {name}",
    )


def verify_evidence() -> None:
    composition = read_gzip_json("composition-qualification.json.gz")
    deterministic = read_gzip_json("deterministic-use-cases.json.gz")
    forks = read_gzip_json("controlled-world-forks.json.gz")
    agent = read_gzip_json("agent-instrument-use.json.gz")

    for name, report in (
        ("composition-qualification.json.gz", composition),
        ("deterministic-use-cases.json.gz", deterministic),
        ("controlled-world-forks.json.gz", forks),
        ("agent-instrument-use.json.gz", agent),
    ):
        verify_sanitization(name, report)

    require(composition.get("status") == "passed", "composition qualification did not pass")
    summary = composition["summary"]
    expected = {
        "reference_units": (64, 64),
        "reference_recipes": (1786, 1786),
        "generated_compositions": (52, 52),
        "unseen_distillation_compositions": (8, 8),
        "module_probes": (32, 32),
        "interface_paths": (7, 7),
        "negative_probes": (192, 192),
        "compile_mutants": (7, 7),
    }
    for key, (passed, denominator) in expected.items():
        require(summary[key]["passed"] == passed, f"unexpected passed count: {key}")
        require(summary[key]["denominator"] == denominator, f"unexpected denominator: {key}")
    require(summary["failure_class_counts"] == {}, "composition failure census changed")
    require(composition["receipt_completeness"]["failures"] == [], "composition failures changed")
    generated_cases = composition["generated_qualification"]["cases"]
    reference_cases = [
        case
        for unit in composition["reference_qualification"]["units"]
        for case in unit["valid_recipe_cases"]
    ]
    require(len(generated_cases) == 52, "generated case census changed")
    require(len(reference_cases) == 1786, "reference recipe census changed")
    require(
        all(case["exact_replay"]["verified"] is True for case in generated_cases + reference_cases),
        "composition replay result changed",
    )

    require(deterministic.get("status") == "passed", "deterministic cases did not pass")
    require(deterministic["summary"]["cases"] == {"passed": 8, "denominator": 8},
            "deterministic case census changed")
    require(deterministic["summary"]["submitted_actions"]["checked"] == 89,
            "submitted-action census changed")
    require(deterministic["summary"]["committed_actions"]["observed"] == 88,
            "committed-action census changed")
    require(deterministic["summary"]["rolled_back_actions"]["observed"] == 1,
            "rollback census changed")
    require(deterministic["failures"] == [], "deterministic failure census changed")
    require(
        all(case["exact_replay"]["verified"] is True for case in deterministic["cases"]),
        "deterministic replay result changed",
    )

    require(forks.get("passed") is True, "controlled world forks did not pass")
    require(forks["pair_count"] == 6 and forks["trace_count"] == 24,
            "controlled-fork census changed")
    require(forks["provider_call_count"] == 0, "controlled-fork provider census changed")
    require(
        all(row["audit"]["passed"] is True for row in forks["rows"]),
        "controlled-fork audit result changed",
    )
    require(
        all(row["audit"]["exact_replay_audit"]["passed"] is True for row in forks["rows"]),
        "controlled-fork replay result changed",
    )

    require(agent.get("status") == "passed", "agent lifecycle did not pass")
    require(agent["summary"]["submitted_action_count"] == 15, "agent action count changed")
    require(agent["summary"]["committed_action_count"] == 15, "agent commit count changed")
    require(agent["summary"]["provider_session_count"] == 1, "agent session census changed")
    require(agent["failures"] == [] and agent["failure_class_counts"] == {},
            "agent failure census changed")
    require(agent["exact_replay"]["verified"] is True, "agent replay did not pass")


def verify_public_boundary(manifest: dict[str, Any]) -> None:
    forbidden_path_parts = ("paper/", "workstreams/", "/draft/", "/interim/", "/pilot/")
    tracked = tracked_files()
    for path in tracked:
        normalized = f"/{path.lower()}"
        require(not path.startswith("paper/"), f"paper path is tracked: {path}")
        require("todo" not in Path(path).name.lower(), f"TODO path is tracked: {path}")
        require(
            not any(part in normalized for part in forbidden_path_parts),
            f"development artifact path is tracked: {path}",
        )

    paths_to_scan = tracked
    for relative in paths_to_scan:
        path = ROOT / relative
        if relative.endswith(".json.gz"):
            with gzip.open(path, "rt", encoding="utf-8") as handle:
                text = handle.read()
        elif relative.endswith(".ipynb"):
            notebook = json.loads(path.read_text(encoding="utf-8"))
            for cell in notebook.get("cells", []):
                for output in cell.get("outputs", []):
                    data = output.get("data")
                    if isinstance(data, dict):
                        data.pop("image/png", None)
                        data.pop("image/jpeg", None)
            text = json.dumps(notebook, sort_keys=True)
        else:
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
        require(_INTERNAL_WORKSTREAM not in text, f"internal workstream leaked: {relative}")
        require(_INTERNAL_TODO not in text, f"internal TODO leaked: {relative}")
        require(_SERVER_PATH.search(text) is None, f"server absolute path leaked: {relative}")
        require(_CREDENTIAL.search(text) is None, f"credential-like text leaked: {relative}")

    require(
        manifest.get("manifest_self_exclusion", {}).get("path") == MANIFEST_RELATIVE,
        "manifest is not the sole declared self-exclusion",
    )


def verify_history() -> None:
    commits = [line for line in git_output("rev-list", "--all").splitlines() if line]
    roots = [line for line in git_output("rev-list", "--max-parents=0", "--all").splitlines() if line]
    require(commits, "Git history is empty")
    require(len(roots) == 1, "Git history does not have exactly one clean root")
    for line in git_output("rev-list", "--objects", "--all").splitlines():
        _, separator, path = line.partition(" ")
        if not separator:
            continue
        lowered = f"/{path.lower()}"
        require(not path.startswith("paper/"), f"paper path exists in Git history: {path}")
        require("todo" not in Path(path).name.lower(), f"TODO path exists in Git history: {path}")
        require("/workstreams/" not in lowered, f"workstream path exists in Git history: {path}")
        require(
            not any(token in lowered for token in ("/draft/", "/interim/", "/pilot/")),
            f"development artifact exists in Git history: {path}",
        )


def verify_tutorials() -> None:
    for name in TUTORIAL_NOTEBOOKS:
        path = ROOT / "notebooks" / name
        require(path.is_file(), f"tutorial notebook is missing: {name}")
        raw = path.read_text(encoding="utf-8")
        require(_TUTORIAL_FORBIDDEN.search(raw) is None, f"forbidden tutorial content: {name}")
        notebook = json.loads(raw)
        metadata = notebook.get("metadata", {}).get("chemworld", {})
        require(metadata.get("runtime_release") == "0.4.0", f"tutorial release mismatch: {name}")
        require(
            metadata.get("output_scope") == "deterministic_public_tutorial",
            f"tutorial output scope mismatch: {name}",
        )
        code_cells = [
            cell for cell in notebook.get("cells", []) if cell.get("cell_type") == "code"
        ]
        require(bool(code_cells), f"tutorial has no code cells: {name}")
        require(
            all(cell.get("execution_count") is not None for cell in code_cells),
            f"tutorial has an unexecuted code cell: {name}",
        )
        require(
            all(
                output.get("output_type") != "error"
                for cell in code_cells
                for output in cell.get("outputs", [])
            ),
            f"tutorial retains an error output: {name}",
        )

    subprocess.run(
        [sys.executable, "scripts/build_readme_visuals.py", "--check"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )


def main() -> int:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    require(isinstance(manifest, dict), "manifest must be a JSON object")
    verify_manifest(manifest)
    verify_evidence()
    verify_public_boundary(manifest)
    verify_history()
    verify_tutorials()
    print(json.dumps({
        "status": "passed",
        "manifest_file_count": len(manifest["files"]),
        "reference_units": "64/64",
        "generated_compositions": "52/52",
        "deterministic_cases": "8/8",
        "controlled_forks": "6 pairs / 24 traces",
        "agent_lifecycles": "1/1",
        "tutorial_notebooks": "3/3 executed and sanitized",
        "git_history": f"1 clean root / {len(git_output('rev-list', '--all').splitlines())} commits",
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
