"""Central pytest taxonomy for selective local validation."""

from __future__ import annotations

from pathlib import Path

import pytest

SLOW_TEST_FILES = frozenset(
    {
        "test_backend_v05_freeze.py",
        "test_end_to_end_notebooks.py",
        "test_environment_self_consistency.py",
        "test_local_eval_machine.py",
        "test_maturity_audit.py",
        "test_maturity_truth_vnext.py",
        "test_physchem_lazy_facade.py",
        "test_provenance_helpers.py",
        "test_public_boundary_security_vnext.py",
        "test_runtime_domain_affordance_audit.py",
        "test_runtime_golden_characterization.py",
        "test_state_transition_invariants.py",
        "test_task_demo_notebooks.py",
        "test_tutorial_notebooks.py",
        "test_wheel_smoke.py",
    }
)
HISTORY_NODE_TOKENS = (
    "compatibility",
    "deprecated",
    "historical",
    "legacy",
    "pre_v0",
    "v01",
)


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Assign orthogonal speed, currency, and subsystem markers to every test."""

    for item in items:
        path = Path(str(item.path))
        filename = path.name
        node_id = item.nodeid.lower()
        item.add_marker(pytest.mark.slow if filename in SLOW_TEST_FILES else pytest.mark.fast)
        item.add_marker(
            pytest.mark.history
            if any(token in node_id for token in HISTORY_NODE_TOKENS)
            else pytest.mark.current
        )
        if filename.startswith("test_rl_"):
            item.add_marker(pytest.mark.rl)
        if "reference" in path.parts or "_reference" in path.stem:
            item.add_marker(pytest.mark.reference)
