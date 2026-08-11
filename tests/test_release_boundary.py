"""Release-boundary tests for the clean v0.2.0 public tree."""

from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
VERIFY_PATH = ROOT / "scripts" / "verify_release.py"


def _load_verifier():  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location("chemworld_release_verifier", VERIFY_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load release verifier")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _manifest() -> dict[str, object]:
    value = json.loads((ROOT / "release" / "manifest.json").read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_manifest_matches_git_and_hashes() -> None:
    verifier = _load_verifier()
    verifier.verify_manifest(_manifest())


@pytest.mark.parametrize("mutation", ["missing", "extra", "hash"])
def test_manifest_fails_closed(mutation: str) -> None:
    verifier = _load_verifier()
    manifest = copy.deepcopy(_manifest())
    rows = manifest["files"]
    assert isinstance(rows, list) and rows
    if mutation == "missing":
        rows.pop()
    elif mutation == "extra":
        rows.append({"path": "unexpected.txt", "bytes": 0, "sha256": "0" * 64})
    else:
        assert isinstance(rows[0], dict)
        rows[0]["sha256"] = "0" * 64
    with pytest.raises(RuntimeError):
        verifier.verify_manifest(manifest)


def test_evidence_denominators_failures_and_replay() -> None:
    _load_verifier().verify_evidence()


def test_public_boundary_and_single_commit_history() -> None:
    verifier = _load_verifier()
    verifier.verify_public_boundary(_manifest())
    verifier.verify_history()


def test_removed_interfaces_stay_removed() -> None:
    assert not (ROOT / "src" / "chemworld" / "eval" / "paper_artifact.py").exists()
    assert not (
        ROOT / "src" / "chemworld" / "eval" / "first_paper_u05_complete_agent.py"
    ).exists()
    assert (ROOT / "src" / "chemworld" / "eval" / "agent_instrument_use.py").is_file()
    completed = subprocess.run(
        [sys.executable, "-m", "chemworld.cli", "--help"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert "paper/preprint" not in completed.stdout


def test_evidence_and_manifest_regeneration_is_idempotent() -> None:
    tracked_before = subprocess.run(
        ["git", "diff", "--", "evidence/reports", "release/manifest.json"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    ).stdout
    subprocess.run(
        [sys.executable, "scripts/sanitize_public_evidence.py"], cwd=ROOT, check=True
    )
    subprocess.run(
        [sys.executable, "scripts/build_release_manifest.py"], cwd=ROOT, check=True
    )
    tracked_after = subprocess.run(
        ["git", "diff", "--", "evidence/reports", "release/manifest.json"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    ).stdout
    assert tracked_after == tracked_before
