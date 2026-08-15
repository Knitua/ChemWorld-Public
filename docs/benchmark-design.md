# Benchmark Design

> **How do we know that an Agent learned to experiment rather than merely scoring well in one fixed world?**

ChemWorld reports task outcomes, constraints, resources, adaptation and autonomy separately. It does not compress unlike physical tasks and interaction levels into one universal intelligence score.

## Evaluation unit

Each campaign is one canonical **Task × Scenario × Agent × Seed** cell. A Task supplies the stable public contract. A World supplies hidden causal rules. A Scenario binds them to an initial state and intervention condition. A Seed reconstructs the instance.

## Three suite roles

- **Confirmatory:** preregistered Agent comparisons on the two designated public task contracts.
- **Diagnostic:** identifiability, feedback use, failure recovery, counterfactual and adaptation attribution.
- **Showcase:** environment coverage, teaching, training and method development without an automatic ranking claim.

## Six reporting axes

1. Task-specific endpoint and practical effect threshold.
2. Operational risk, legality and failure count.
3. Experiment, measurement, sample and process cost.
4. Adaptation speed after a controlled world shift.
5. Information efficiency and uncertainty reduction.
6. Method resources: training compute, environment steps, tokens, cost and latency.

An endpoint improvement does not erase an undeclared risk or resource regression.

## Generalization axes are different

New seeds test instance randomness. Parameter extrapolation tests range shift. New mechanism families test causal adaptation. Independent backends test simulator-specific shortcuts. Real data and physical systems test bridge validity. None substitutes for another.

## Trust chain

```text
submission → trajectory validation → deterministic replay
→ metric recomputation → constraint/resource audit → verified result
```

Formal comparisons should freeze the release and task hashes, Agent and provider identity, prompts or policy configuration, feedback condition, resource limits, seeds, failure policy, exclusion rules, primary metric and uncertainty analysis before running the confirmation set.

## Current public status

The Public v0.4 engine, validation, replay and finite qualification evidence are operational. The repository does not bundle a completed cross-method Agent ranking or mechanism-adaptation leaderboard. The browser comparison is for behavioral inspection; results from one task and seed must not be promoted to a benchmark claim.

See [Confirmatory Tasks](confirmatory-tasks.md), [Evidence & Current Status](evidence.md) and [Limitations](limitations.md).
