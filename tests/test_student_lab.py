from __future__ import annotations

import ast
import json
import threading
import time
from http.client import HTTPConnection
from pathlib import Path

from chemworld.cli import build_parser
from chemworld.lab.agent_run import AgentRunManager, agent_catalog
from chemworld.lab.limits import LabCapacityError
from chemworld.lab.server import LabLimits, LabServer, serve
from chemworld.lab.session import LabSession, LabSessionManager, task_catalog

ROOT = Path(__file__).resolve().parents[1]


def test_lab_catalog_and_cli_default_to_loopback() -> None:
    cards = task_catalog()
    assert cards[0]["task_id"] == "reaction-to-assay"
    assert all(card["student_goal"] for card in cards)
    partition = next(card for card in cards if card["task_id"] == "partition-discovery")
    assert partition["apparatus_family"] == "separation"
    assert "separate_phase" in partition["allowed_operations"]
    args = build_parser().parse_args(["lab", "--no-browser"])
    assert args.host == "127.0.0.1"
    assert args.port == 8876
    assert args.no_browser is True
    assert args.public is False


def test_browser_agent_catalog_is_provider_free() -> None:
    cards = agent_catalog()
    assert cards[0]["agent_id"] == "scripted_chemistry"
    assert all(card["uses_model"] is False for card in cards)
    assert {card["agent_id"] for card in cards} >= {
        "scripted_chemistry",
        "safe_gp_bo",
        "llm_replay",
    }
    manager = AgentRunManager()
    try:
        try:
            manager.create("reaction-to-assay", "codex_subagent_replay", seed=0)
        except ValueError as exc:
            assert "not exposed" in str(exc)
        else:  # pragma: no cover - defensive assertion
            raise AssertionError("non-catalog Agent was accepted by the browser Lab")
    finally:
        manager.close_all()


def test_lab_rejects_non_loopback_bind_address() -> None:
    try:
        serve("0.0.0.0", 8876, open_browser=False)
    except ValueError as exc:
        assert "loopback" in str(exc)
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("non-loopback Student Lab bind was accepted")


def test_public_lab_resource_managers_fail_closed_at_capacity() -> None:
    sessions = LabSessionManager(max_sessions=1, session_ttl_s=60)
    agents = AgentRunManager(max_runs=4, max_concurrent_runs=1, run_ttl_s=60)
    try:
        sessions.create("reaction-to-assay", seed=0)
        try:
            sessions.create("reaction-to-assay", seed=1)
        except LabCapacityError as exc:
            assert "session capacity" in str(exc)
        else:  # pragma: no cover - defensive assertion
            raise AssertionError("bounded public Lab accepted too many sessions")

        try:
            agents.compare("reaction-to-assay", ["scripted_chemistry", "llm_replay"], seed=0)
        except LabCapacityError as exc:
            assert "comparison capacity" in str(exc)
        else:  # pragma: no cover - defensive assertion
            raise AssertionError("bounded public Lab accepted too many concurrent agents")
    finally:
        sessions.close_all()
        agents.close_all()


def test_public_http_mode_exposes_health_headers_and_rate_limit() -> None:
    server = LabServer(
        ("127.0.0.1", 0),
        public=True,
        limits=LabLimits(max_sessions=2, post_rate_per_minute=1),
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    connection = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
    try:
        connection.request("GET", "/api/health")
        health = connection.getresponse()
        payload = json.loads(health.read())
        assert payload["public_mode"] is True
        assert payload["provider_required"] is False
        assert health.getheader("X-Frame-Options") == "DENY"
        assert health.getheader("Strict-Transport-Security")

        body = json.dumps({"task_id": "reaction-to-assay", "seed": 0})
        headers = {"Content-Type": "application/json"}
        connection.request("POST", "/api/sessions", body, headers)
        created = connection.getresponse()
        assert created.status == 201
        created.read()

        connection.request("POST", "/api/sessions", body, headers)
        limited = connection.getresponse()
        assert limited.status == 429
        assert "rate limit" in json.loads(limited.read())["error"]
    finally:
        connection.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


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


def test_lab_state_exposes_locked_actions_and_cumulative_public_apparatus() -> None:
    session = LabSession("partition-discovery", seed=0)
    try:
        initial = session.state()
        actions = {item["operation"]: item for item in initial["all_actions"]}
        assert initial["public_vessel"]["apparatus_family"] == "separation"
        assert actions["add_phase"]["valid"] is True
        assert actions["separate_phase"]["valid"] is False
        assert "先完成混合并静置分层。" in actions["separate_phase"]["lock_reasons"]

        stepped = session.step(
            {"operation": "add_phase", "phase": "aqueous", "volume_L": 0.02}
        )
        assert stepped["accepted"] is True
        assert stepped["state"]["public_vessel"]["phase_active"] is True
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

        connection.request("GET", "/agent/")
        agent_page = connection.getresponse()
        assert agent_page.status == 200
        assert b"ChemWorld Agent Observatory" in agent_page.read()

        connection.request("GET", "/api/agents")
        agents = connection.getresponse()
        assert agents.status == 200
        assert json.loads(agents.read())["online_providers_enabled"] is False

        agent_body = json.dumps(
            {
                "task_id": "reaction-to-assay",
                "agent_id": "scripted_chemistry",
                "seed": 0,
            }
        )
        connection.request(
            "POST", "/api/agent-runs", agent_body, {"Content-Type": "application/json"}
        )
        agent_created = connection.getresponse()
        agent_state = json.loads(agent_created.read())
        assert agent_created.status == 201

        command = json.dumps({"command": "step"})
        connection.request(
            "POST",
            f"/api/agent-runs/{agent_state['run_id']}/commands",
            command,
            {"Content-Type": "application/json"},
        )
        commanded = connection.getresponse()
        assert commanded.status == 200
        commanded.read()

        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            connection.request("GET", f"/api/agent-runs/{agent_state['run_id']}")
            fetched = connection.getresponse()
            agent_state = json.loads(fetched.read())
            if agent_state["status"] == "paused":
                break
            time.sleep(0.02)
        assert agent_state["step_count"] == 1
        assert agent_state["records"][0]["transaction_status"] == "committed"

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


def test_agent_run_supports_step_then_continue_with_official_records() -> None:
    manager = AgentRunManager()
    run = manager.create("reaction-to-assay", "scripted_chemistry", seed=0)
    try:
        run.step()
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            state = run.state()
            if state["status"] == "paused" and state["step_count"] == 1:
                break
            time.sleep(0.01)
        else:
            raise AssertionError(f"agent run did not pause after one step: {run.state()}")

        record = state["records"][0]
        assert record["action"]["operation"] == "add_solvent"
        assert record["decision_context"]["available_operations"]
        assert record["method_resources"]["accounting_complete"] is True

        run.run()
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            state = run.state()
            if state["status"] in {"completed", "failed"}:
                break
            time.sleep(0.02)
        assert state["status"] == "completed", state["error"]
        assert state["records"][-1]["event_type"] == "experiment_end"
        assert any(record["spectra"] for record in state["records"])
    finally:
        manager.close_all()


def test_agent_comparison_uses_same_task_and_seed() -> None:
    manager = AgentRunManager()
    try:
        comparison = manager.compare(
            "reaction-to-assay", ["scripted_chemistry", "llm_replay"], seed=0
        )
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            state = manager.comparison_state(comparison.comparison_id)
            if state["status"] in {"completed", "failed"}:
                break
            time.sleep(0.03)
        assert state["status"] == "completed"
        assert {item["agent_id"] for item in state["runs"]} == {
            "scripted_chemistry",
            "llm_replay",
        }
        assert all(item["step_count"] > 0 for item in state["runs"])
    finally:
        manager.close_all()
