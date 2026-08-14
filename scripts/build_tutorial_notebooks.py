#!/usr/bin/env python3
# ruff: noqa: E501, RUF001
"""Build and execute the three deterministic public tutorial notebooks."""

from __future__ import annotations

import argparse
import copy
import json
import os
import re
from pathlib import Path
from typing import Any

import nbformat
from nbclient import NotebookClient

ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK_ROOT = ROOT / "notebooks"
NOTEBOOK_SCHEMA_VERSION = "chemworld-public-tutorial-notebook-0.4"
_SERVER_PATHS = ("/" + "mnt/afs/", "/" + "root/")
FORBIDDEN = re.compile(
    r"private[-_ ]?eval|workstreams?|first_paper|paper[_ /-]?2|arxiv|"
    + "|".join(re.escape(path) for path in _SERVER_PATHS)
    + r"|api[_ -]?key|authorization:\s*bearer",
    re.IGNORECASE,
)


def _markdown(source: str) -> Any:
    return nbformat.v4.new_markdown_cell(source.strip() + "\n")


def _code(source: str) -> Any:
    return nbformat.v4.new_code_cell(source.strip() + "\n")


def _setup_cell() -> Any:
    return _code(
        r'''
import importlib.util
import subprocess
import sys

if importlib.util.find_spec("google") is not None and importlib.util.find_spec("google.colab") is not None:
    subprocess.check_call([
        sys.executable,
        "-m",
        "pip",
        "install",
        "-q",
        "chemworld-bench[notebooks] @ git+https://github.com/Knitua/ChemWorld-Public.git@v0.4.0",
    ])

import gymnasium as gym
import matplotlib.pyplot as plt
import pandas as pd
from IPython.display import display

import chemworld

pd.set_option("display.max_columns", 20)
pd.set_option("display.precision", 4)
plt.rcParams.update({"figure.figsize": (9, 3.8), "figure.dpi": 110})
print(f"ChemWorld {chemworld.__version__} · provider-free deterministic tutorial")
'''
    )


def _runner_cell() -> Any:
    return _code(
        r'''
def run_recipe(task_id: str, recipe: list[dict], *, seed: int = 0) -> tuple[pd.DataFrame, dict]:
    """Execute typed actions while retaining public validation and resource fields."""
    env = gym.make("ChemWorld", task_id=task_id, seed=seed)
    _observation, info = env.reset(seed=seed)
    rows = []
    final_info = info
    try:
        for step, action in enumerate(recipe, start=1):
            validation = env.unwrapped.validate_action(action)
            _observation, reward, terminated, truncated, info = env.step(action)
            final_info = dict(info)
            rows.append({
                "step": step,
                "operation": action["operation"],
                "valid": bool(validation["valid"]),
                "transaction": info.get("transaction_status"),
                "reward": float(reward),
                "leaderboard_score": info.get("leaderboard_score"),
                "cost_total": info.get("cost"),
                "cost_delta": info.get("cost_delta"),
                "sample_delta_L": info.get("sample_delta"),
                "risk_delta": info.get("risk_delta"),
                "observed_keys": ", ".join(info.get("observed_keys", ())),
                "terminated": bool(terminated),
                "truncated": bool(truncated),
            })
            if terminated or truncated:
                break
    finally:
        env.close()
    frame = pd.DataFrame(rows)
    assert frame["valid"].all(), "Every tutorial request must validate before execution."
    assert frame["transaction"].eq("committed").all(), "Every tutorial action must commit."
    return frame, final_info
'''
    )


def _first_experiment() -> Any:
    cells = [
        _markdown(
            """
# 01 · Your first complete ChemWorld experiment

**Goal.** Read the public Reaction-to-Assay contract, validate a typed recipe, collect intermediate HPLC feedback, terminate explicitly and inspect the final assay and resource ledger.

> 中文提示：本教程逐步展示 Agent 能看到的公开接口与观测，不读取隐藏世界状态，也不调用外部模型 Provider。

This is a reproducible interface walkthrough, not an optimized chemical procedure.
"""
        ),
        _setup_cell(),
        _markdown("## 1. Inspect the public contract before acting"),
        _code(
            r'''
env = gym.make("ChemWorld", task_id="reaction-to-assay", seed=0)
_observation, _info = env.reset(seed=0)
prompt = env.unwrapped.task_prompt()
contract = pd.DataFrame({
    "field": ["task_id", "objective", "episode_mode", "allowed_instruments", "success_metrics", "safety_limit"],
    "public value": [
        prompt["task_id"], prompt["objective"], prompt["episode_mode"],
        prompt["allowed_instruments"], prompt["success_metrics"], prompt["safety_limit"],
    ],
})
display(contract)

heat_schema = env.unwrapped.action_schema("heat")
display(pd.DataFrame(heat_schema["fields"])[["field", "unit", "required", "bounds"]])
env.close()
'''
        ),
        _markdown("## 2. Define a typed action sequence"),
        _code(
            r'''
recipe = [
    {"operation": "add_solvent", "volume_L": 0.030, "solvent": 1},
    {"operation": "add_reagent", "amount_mol": 0.012},
    {"operation": "add_catalyst", "catalyst": 2, "catalyst_amount_mol": 0.0004},
    {"operation": "heat", "target_temperature_K": 350.0, "duration_s": 1200.0, "stirring_speed_rpm": 800.0},
    {"operation": "sample", "sample_volume_L": 0.0005},
    {"operation": "measure", "instrument": "hplc"},
    {"operation": "quench"},
    {"operation": "terminate"},
    {"operation": "measure", "instrument": "final_assay"},
]
display(pd.DataFrame([
    {"step": step, "operation": action["operation"], "public payload": {k: v for k, v in action.items() if k != "operation"}}
    for step, action in enumerate(recipe, start=1)
]))
'''
        ),
        _runner_cell(),
        _markdown("## 3. Execute, observe and account for resources"),
        _code(
            r'''
trace, final_info = run_recipe("reaction-to-assay", recipe, seed=0)
display(trace)

assert trace.iloc[-2]["operation"] == "terminate"
assert trace.iloc[-1]["operation"] == "measure"
assert final_info.get("instrument") == "final_assay"
'''
        ),
        _markdown("## 4. See how the public signal changes across the lifecycle"),
        _code(
            r'''
plot_frame = trace.assign(
    visible_score=trace["leaderboard_score"].where(trace["leaderboard_score"].notna(), trace["reward"])
)
ax = plot_frame.plot(x="step", y="visible_score", marker="o", color="#087f73", legend=False)
ax.set(title="Public score signal after each committed action", ylabel="visible score", xticks=trace["step"])
ax.grid(alpha=0.2)
plt.show()

metrics = final_info.get("processed_estimate", {})
metric_names = ["conversion", "yield", "selectivity", "purity", "safety_risk"]
display(pd.DataFrame([
    {"metric": name, "public final estimate": metrics.get(name)} for name in metric_names
]))
display(pd.DataFrame([{
    "total cost": final_info.get("cost"),
    "last sample delta / L": final_info.get("sample_delta"),
    "final leaderboard score": final_info.get("leaderboard_score"),
    "transaction": final_info.get("transaction_status"),
}]))
'''
        ),
        _markdown(
            """
## 5. Make the next decision explicit

A useful Agent should turn observations into a falsifiable next experiment. The statement below is deliberately modest: it records a hypothesis and one changed control, rather than claiming the mechanism is known.
"""
        ),
        _code(
            r'''
next_decision = {
    "current_evidence": "Product is measurable after the 350 K intervention; the final assay closes the lifecycle.",
    "hypothesis": "A shorter heat duration may retain conversion while reducing process exposure.",
    "next_experiment": {"target_temperature_K": 350.0, "duration_s": 900.0},
    "hold_fixed": ["materials", "catalyst", "instrument schedule", "seed"],
}
next_decision
'''
        ),
    ]
    return _notebook("01_first_experiment", cells)


def _purification() -> Any:
    cells = [
        _markdown(
            """
# 02 · Reaction to purification

**Goal.** Continue a reaction through phase setup, extraction, wash, drying and concentration while keeping validation, transaction and measurement receipts visible.

> 中文提示：重点是“操作—观测—资源”的完整记录，不是寻找最高分 recipe。
"""
        ),
        _setup_cell(),
        _markdown("## 1. Inspect purification affordances"),
        _code(
            r'''
env = gym.make("ChemWorld", task_id="reaction-to-purification", seed=0)
_observation, _info = env.reset(seed=0)
prompt = env.unwrapped.task_prompt()
display(pd.DataFrame({
    "field": ["task_id", "objective", "episode_mode", "success_metrics", "allowed_instruments"],
    "public value": [prompt["task_id"], prompt["objective"], prompt["episode_mode"], prompt["success_metrics"], prompt["allowed_instruments"]],
}))
for operation in ("add_extractant", "separate_phase", "wash", "concentrate"):
    schema = env.unwrapped.action_schema(operation)
    print(operation, "→", schema["required_fields"])
env.close()
'''
        ),
        _markdown("## 2. Define the reaction-to-purification recipe"),
        _code(
            r'''
recipe = [
    {"operation": "add_solvent", "volume_L": 0.030, "solvent": 1},
    {"operation": "add_reagent", "amount_mol": 0.012},
    {"operation": "add_catalyst", "catalyst": 2, "catalyst_amount_mol": 0.0004},
    {"operation": "heat", "target_temperature_K": 350.0, "duration_s": 1200.0, "stirring_speed_rpm": 800.0},
    {"operation": "quench"},
    {"operation": "add_phase", "phase": "organic", "volume_L": 0.020},
    {"operation": "add_extractant", "extractant": "organic", "volume_L": 0.010},
    {"operation": "mix", "duration_s": 120.0, "stirring_speed_rpm": 600.0},
    {"operation": "settle", "duration_s": 300.0},
    {"operation": "separate_phase", "target_phase": "organic"},
    {"operation": "wash", "wash_volume_L": 0.010},
    {"operation": "dry"},
    {"operation": "concentrate", "duration_s": 300.0},
    {"operation": "terminate"},
    {"operation": "measure", "instrument": "final_assay"},
]
display(pd.DataFrame([
    {"step": step, "operation": action["operation"], "public payload": {k: v for k, v in action.items() if k != "operation"}}
    for step, action in enumerate(recipe, start=1)
]))
'''
        ),
        _runner_cell(),
        _markdown("## 3. Execute the complete lifecycle"),
        _code(
            r'''
trace, final_info = run_recipe("reaction-to-purification", recipe, seed=0)
display(trace)
assert final_info.get("instrument") == "final_assay"
assert not trace["truncated"].any()
'''
        ),
        _markdown("## 4. Read the purity–recovery–cost trade-off"),
        _code(
            r'''
metrics = final_info.get("processed_estimate", {})
tradeoff = pd.DataFrame([{
    "purity": metrics.get("purity"),
    "recovery": metrics.get("recovery"),
    "yield": metrics.get("yield"),
    "mass-balance error": metrics.get("process_mass_balance_error"),
    "safety risk": metrics.get("safety_risk"),
    "total cost": final_info.get("cost"),
    "leaderboard score": final_info.get("leaderboard_score"),
}])
display(tradeoff)

visible = tradeoff[["purity", "recovery", "safety risk"]].T.rename(columns={0: "public estimate"})
ax = visible.plot(kind="bar", color="#356fe3", legend=False)
ax.set(title="Final public purification trade-off", ylim=(0, 1.05), ylabel="public estimate")
ax.grid(axis="y", alpha=0.2)
plt.xticks(rotation=0)
plt.show()
'''
        ),
        _markdown("## 5. Choose one controlled follow-up"),
        _code(
            r'''
follow_up = {
    "question": "Does a larger organic phase improve recovery without losing purity?",
    "change_one_control": {"add_phase_volume_L": 0.030},
    "hold_fixed": ["reaction conditions", "extractant identity", "mix/settle times", "target phase", "seed"],
    "readouts": ["purity", "recovery", "process_mass_balance_error", "cost"],
}
follow_up
'''
        ),
    ]
    return _notebook("02_reaction_to_purification", cells)


def _world_change() -> Any:
    cells = [
        _markdown(
            """
# 03 · Controlled world change

**Goal.** As an experiment author, construct a parent and child world that share the public contract and typed action sequence while one registered world component changes. Compare only public terminal feedback.

> 中文提示：世界组件身份属于作者端控制；面向 Agent 的输入不包含这项答案信息。

This notebook demonstrates the released world-foundation API. It does not report an ongoing research experiment.
"""
        ),
        _setup_cell(),
        _markdown("## 1. Resolve the packaged qualification configuration"),
        _code(
            r'''
from importlib.resources import files
from pathlib import Path

from chemworld.foundation.world_fork_manifest import load_world_component_inventory
from chemworld.foundation.world_fork_runtime import (
    load_world_fork_qualification_config,
    run_runtime_world_fork,
)

def config_file(relative: str) -> Path:
    repo_path = Path("configs") / relative
    if repo_path.is_file():
        return repo_path
    return Path(str(files("chemworld").joinpath("resources", "configs", relative)))

config = load_world_fork_qualification_config(
    config_file("benchmark/work_i_world_fork_qualification_v0.1.json")
)
inventory = load_world_component_inventory(
    config_file("benchmark/work_i_world_fork_component_inventory_v0.1.json")
)
case = next(item for item in config["cases"] if item["case_id"] == "partition-constitutive-law-family")
display(pd.DataFrame([{
    "task": case["task_id"],
    "world variants": "parent + child",
    "seed": 0,
    "provider calls": 0,
    "public experiment policy": config["action_policy"]["policy_id"],
}]))
'''
        ),
        _markdown("## 2. Build and execute the fork"),
        _code(
            r'''
runtime = run_runtime_world_fork(
    inventory=inventory,
    task_id=case["task_id"],
    seed=0,
    intervention_class=case["intervention_class"],
    target_component_id=case["target_component_id"],
    intervention_payload=case["intervention_payload"],
)

changed = runtime["fork_spec"]["component_diff"]["changed_component_ids"]
gates = pd.DataFrame([{
    "changed component count": len(changed),
    "same public action sequence": runtime["execution"]["same_action_sequence"],
    "parent actions committed": runtime["execution"]["parent_all_actions_committed"],
    "child actions committed": runtime["execution"]["child_all_actions_committed"],
    "parent exact replay": runtime["exact_replay"]["variant_matches"]["parent"],
    "child exact replay": runtime["exact_replay"]["variant_matches"]["child"],
    "provider calls": runtime["provider_call_count"],
}])
display(gates)

assert changed == [case["target_component_id"]]
assert runtime["execution"]["passed"] is True
assert runtime["exact_replay"]["passed"] is True
assert runtime["provider_call_count"] == 0
'''
        ),
        _markdown("## 3. Confirm that the public experiment stayed fixed"),
        _code(
            r'''
parent = runtime["traces"]["parent"]
child = runtime["traces"]["child"]
assert parent["action_sequence"] == child["action_sequence"]

display(pd.DataFrame([
    {"step": index, "operation": action["operation"], "same in parent and child": True}
    for index, action in enumerate(parent["action_sequence"], start=1)
]))
'''
        ),
        _markdown("## 4. Compare public terminal feedback"),
        _code(
            r'''
parent_public = parent["checkpoints"]["terminal_assay"]["public_observation"]
child_public = child["checkpoints"]["terminal_assay"]["public_observation"]
metrics = ["product_in_organic", "product_in_aqueous", "phase_ratio", "purity", "recovery", "score"]
comparison = pd.DataFrame([
    {"metric": metric, "World A": parent_public.get(metric), "World B": child_public.get(metric)}
    for metric in metrics
])
comparison["signed change"] = comparison["World B"] - comparison["World A"]
display(comparison)

ax = comparison.set_index("metric")[["World A", "World B"]].plot(kind="bar", color=["#356fe3", "#229960"])
ax.set(title="Same public intervention, different public response", ylabel="public terminal value")
ax.grid(axis="y", alpha=0.2)
plt.xticks(rotation=25, ha="right")
plt.tight_layout()
plt.show()
'''
        ),
        _markdown(
            """
## 5. Ask a mechanism-level question

Free-form explanations are difficult to score reliably. A controlled study can instead ask the Agent to choose a registered directional statement after repeated experiments.
"""
        ),
        _code(
            r'''
mechanism_check = {
    "evidence_available_to_agent": ["typed actions", "public instrument observations", "resource receipts"],
    "question": "Relative to World A, what direction best describes World B's product-in-organic response under the fixed intervention?",
    "choices": ["increases", "decreases", "no detectable change", "insufficient evidence"],
    "scoring_note": "Score the selected direction against the registered evaluator; do not expose the author-side component label.",
}
mechanism_check
'''
        ),
    ]
    return _notebook("03_controlled_world_change", cells)


def _notebook(notebook_id: str, cells: list[Any]) -> Any:
    return nbformat.v4.new_notebook(
        cells=cells,
        metadata={
            "chemworld": {
                "schema_version": NOTEBOOK_SCHEMA_VERSION,
                "notebook_id": notebook_id,
                "runtime_release": "0.4.0",
                "seed_policy": "fixed_zero",
                "output_scope": "deterministic_public_tutorial",
            },
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python"},
        },
    )


def notebook_sources() -> dict[Path, Any]:
    return {
        NOTEBOOK_ROOT / "01_first_experiment.ipynb": _first_experiment(),
        NOTEBOOK_ROOT / "02_reaction_to_purification.ipynb": _purification(),
        NOTEBOOK_ROOT / "03_controlled_world_change.ipynb": _world_change(),
    }


def _normalize(notebook: Any) -> Any:
    value = copy.deepcopy(notebook)
    value.metadata = {
        "chemworld": dict(value.metadata["chemworld"]),
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python"},
    }
    for index, cell in enumerate(value.cells):
        cell["id"] = f"cell-{index:02d}"
        cell.metadata = {}
        if cell.cell_type != "code":
            continue
        for output in cell.get("outputs", []):
            if "metadata" in output:
                output["metadata"] = {}
            if output.get("output_type") == "error":
                output["traceback"] = [re.sub(r"\x1b\[[0-9;]*m", "", line) for line in output["traceback"]]
    return value


def _execute(source: Any) -> Any:
    notebook = copy.deepcopy(source)
    old_cwd = Path.cwd()
    os.environ.setdefault("PYTHONHASHSEED", "0")
    try:
        os.chdir(ROOT)
        client = NotebookClient(
            notebook,
            timeout=900,
            kernel_name="python3",
            allow_errors=False,
            resources={"metadata": {"path": str(ROOT)}},
        )
        executed = client.execute(cwd=str(ROOT))
    finally:
        os.chdir(old_cwd)
    return _normalize(executed)


def _serialized(notebook: Any) -> str:
    return nbformat.writes(_normalize(notebook), version=4) + "\n"


def _assert_public(path: Path, content: str) -> None:
    match = FORBIDDEN.search(content)
    if match:
        raise RuntimeError(f"forbidden tutorial content in {path.name}: {match.group(0)!r}")
    payload = json.loads(content)
    for cell in payload["cells"]:
        if cell["cell_type"] == "code" and any(
            output.get("output_type") == "error" for output in cell.get("outputs", [])
        ):
            raise RuntimeError(f"error output retained in {path.name}")


def build(*, check: bool) -> dict[str, Any]:
    NOTEBOOK_ROOT.mkdir(parents=True, exist_ok=True)
    summaries = []
    for path, source in notebook_sources().items():
        executed = _execute(source)
        content = _serialized(executed)
        _assert_public(path, content)
        if check:
            if not path.is_file() or path.read_text(encoding="utf-8") != content:
                raise RuntimeError(f"generated notebook is stale: {path.relative_to(ROOT)}")
        else:
            with path.open("w", encoding="utf-8", newline="\n") as handle:
                handle.write(content)
        summaries.append(
            {
                "path": path.relative_to(ROOT).as_posix(),
                "code_cells": sum(cell.cell_type == "code" for cell in executed.cells),
                "output_cells": sum(bool(cell.get("outputs")) for cell in executed.cells),
            }
        )
    return {"status": "checked" if check else "written", "notebooks": summaries}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    print(json.dumps(build(check=args.check), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
