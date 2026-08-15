# Getting Started

Choose the shortest path that matches what you want to learn.

## Try without installing

- [Open the live Student Lab](https://chemworld-public-lab.onrender.com/student/) to choose a task and compose legal actions.
- [Open the Agent Observatory](https://chemworld-public-lab.onrender.com/agent/) to step through eight provider-free policies.
- [Run the first experiment in Colab](https://colab.research.google.com/github/Knitua/ChemWorld-Public/blob/v0.4.0/notebooks/01_first_experiment.ipynb) with retained deterministic outputs.

The free Render service may need a short wake-up after an idle period.

## Run locally

```bash
git clone https://github.com/Knitua/ChemWorld-Public.git
cd ChemWorld-Public
python -m pip install -e .
chemworld lab
```

Open `http://127.0.0.1:8876/student/` or `http://127.0.0.1:8876/agent/`. The default server binds only to loopback.

## Run one Agent episode

```bash
chemworld tasks list
chemworld run --task reaction-to-assay --agent scripted_chemistry --seed 0
```

The command writes a trajectory and manifest under `runs/`. Verify and evaluate the printed trajectory path:

```bash
chemworld verify --constitution --submission runs/<trajectory>.jsonl
chemworld evaluate --submission runs/<trajectory>.jsonl
```

## Write your own Agent

Implement the small `BaseAgent` protocol and pass the instance to `run_agent`. Start with the complete example in [Build an Agent](agents.md). Provider adapters are opt-in Python workflows; the public Lab remains provider-free and never accepts arbitrary visitor code.

## Learn the contracts

Read [One Complete Experiment](one-experiment.md) for the lifecycle, [System Model](architecture.md) for ownership boundaries, and [API Reference](reference.md) for the runtime surface. For a deeper command-by-command tutorial, the historical [installation walkthrough](getting_started.md) remains available.
