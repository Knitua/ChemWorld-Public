from __future__ import annotations

import ast
import json
import threading
from http.client import HTTPConnection
from pathlib import Path

from chemworld.cli import build_parser
from chemworld.lab.server import LabServer, serve
from chemworld.lab.session import LabSession, task_catalog

ROOT = Path(__file__).resolve().parents[1]


def test_lab_catalog_and_cli_default_to_loopback() -> None:
    cards = task_catalog()
    assert cards[0]["task_id"] == "reaction-to-assay"
    assert all(card["student_goal"] for card in cards)
    args = build_parser().parse_args(["lab", "--no-browser"])
    assert args.host == "127.0.0.1"
    assert args.port == 8876
    assert args.no_browser is True


def test_lab_rejects_non_loopback_bind_address() -> None:
    try:
        serve("0.0.0.0", 8876, open_browser=False)
    except ValueError as exc:
        assert "loopback" in str(exc)
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("non-loopback Student Lab bind was accepted")


def test_rejected_action_does_not_spend_budget_and_valid_action_animates() -> None:
    session = LabSession("reaction-to-assay", seed=0)
    try:
        before = session.state()
        rejected = session.step({"operation": "heat", "target_temperature_K": 350.0})
        assert rejected["accepted"] is False
        assert rejected["state"]["campaign_state"]["operation_count"] == 0
        accepted = session.step(
            {"operation": "add_solvent", "volume_L": 0.03, "solvent": 1}
        )
        assert accepted["accepted"] is True
        assert accepted["record"]["state_effects"]["visual"] == "feed"
        assert accepted["state"]["campaign_state"]["operation_count"] == 1
        assert before["campaign_state"]["remaining_budget"] - 1 == (
            accepted["state"]["campaign_state"]["remaining_budget"]
        )
    finally:
        session.close()


def test_loopback_http_api_serves_assets_and_executes_action() -> None:
    server = LabServer(("127.0.0.1", 0))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    connection = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
    try:
        connection.request("GET", "/api/health")
        health = connection.getresponse()
        assert health.status == 200
        assert json.loads(health.read())["provider_required"] is False

        connection.request("GET", "/")
        page = connection.getresponse()
        assert page.status == 200
        assert b"ChemWorld Student Lab" in page.read()

        body = json.dumps({"task_id": "reaction-to-assay", "seed": 0})
        connection.request("POST", "/api/sessions", body, {"Content-Type": "application/json"})
        created = connection.getresponse()
        state = json.loads(created.read())
        assert created.status == 201

        action = json.dumps(
            {"action": {"operation": "add_solvent", "volume_L": 0.03, "solvent": 1}}
        )
        connection.request(
            "POST",
            f"/api/sessions/{state['session_id']}/actions",
            action,
            {"Content-Type": "application/json"},
        )
        stepped = connection.getresponse()
        assert stepped.status == 200
        assert json.loads(stepped.read())["accepted"] is True
    finally:
        connection.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_lab_python_surface_has_no_provider_imports() -> None:
    lab_root = ROOT / "src" / "chemworld" / "lab"
    imported: set[str] = set()
    for path in lab_root.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
    assert not any(name.startswith("chemworld.providers") for name in imported)
    assert not any(name.startswith("chemworld.agents") for name in imported)
