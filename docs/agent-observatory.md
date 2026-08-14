# Agent Observatory

Agent Observatory is the provider-free policy workbench included with `chemworld lab`. It is for
understanding how an Agent acts through the public ChemWorld contract—not for displaying private
reasoning or claiming leaderboard performance.

```bash
chemworld lab
```

Open `http://127.0.0.1:8876/agent/`. The adjacent `/student/` route remains the manual workbench.

## What is connected

The browser starts the official `run_agent()` execution path. Every policy therefore receives the
same public decision context as a normal CLI run, and every request goes through the normal action
validator and transactional environment. The initial catalog includes deterministic reference and
replay policies, seeded design and search baselines, and safety-constrained Bayesian optimization.
No entry calls an online model.

The Observatory does not fabricate an Agent rationale. It displays only structured trace fields
actually emitted by that Agent, alongside the runner's independent decision audit.

## Run controls and replay

- **Single step** grants exactly one action, then pauses at the next public step boundary.
- **Run continuously** continues to task termination; **pause** takes effect at a step boundary.
- The timeline can revisit any committed or rejected action without re-running the environment.
- **Download JSON** exports the public Observatory projection. Use the CLI JSONL artifact for formal
  replay verification and evaluation.

Spectral plots are downsampled for responsive rendering. Their source is the public instrument
signal returned by the environment; they do not reconstruct hidden chemical state.

## Exploratory comparison

The comparison panel runs two to four provider-free policies on exactly the same task and seed and
shows endpoint score, cost, safety risk and step count. A single-seed comparison is useful for
debugging behavior but is not evidence that one policy is generally superior. Formal comparisons
must fix task versions, policy versions, seeds, method-resource limits and evaluation protocol.

## Why online providers are not one click

ChemWorld supports custom Python Agents and optional DeepSeek and Codex adapters. They stay in the
explicit Python API because live runs require credential handling, model identity, prompt-contract
provenance, retry policy and resource limits. See [Connect an agent](agents.md) for those paths.

The local web server binds only to loopback, has no authentication, stores runs in memory and sends
no data to an external service.
