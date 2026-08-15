# System Model

ChemWorld separates physical truth, experimental interaction and research objectives. This prevents hidden evaluator state from leaking into the Agent interface and prevents task scores from being mistaken for physical quantities.

## Three layers

| Layer | Owns | Does not own |
| --- | --- | --- |
| Physical Causal World | Typed state, hidden transitions, constitutive laws, equipment, observation generation and controlled interventions | Task objectives, Agent beliefs or rankings |
| Experimental Interaction Runtime | Action validity, atomic transactions, lifecycle, measurements, failures, resources and replayable trajectories | Agent action selection or silent repair |
| Task and Evaluation Contract | Public goal, permissions, budgets, termination and task-specific evaluation | Runtime physics or disclosure of hidden truth |

## Canonical hierarchy

```text
Campaign
└── Experiment
    └── Operation / Measurement
```

A campaign is one **Task × Scenario × Agent × Seed** cell. An experiment begins from an explicit initialized state and ends in final assay, explicit termination, failure or budget truncation. Only a contract-valid final assay is a comparable formal endpoint; failed and incomplete attempts remain part of the trajectory.

## Three action abstractions

- **Campaign Design:** select a complete recipe or experiment.
- **Procedure Execution:** choose one legal operation at a time.
- **Process Control:** choose bounded equipment setpoints or process actions.

Public v0.4 supports these abstractions through the same task and runtime contracts. Process Control is a bounded setpoint abstraction, not a claim of universal high-frequency control.

## Atomic validation

Before an operation commits, the runtime checks its schema, task permission, parameter bounds, apparatus state, material preconditions and remaining resources. A rejected operation returns public reasons and leaves state and budget unchanged. A committed operation updates the material, apparatus, resource and event ledgers together.

## Outcome separation

Trajectories distinguish:

- `environment_outcome`: what the world and runtime produced;
- `agent_visible_observation`: what this information condition released;
- `evaluation_outcome`: the bound endpoint and evaluation fields.

Changing feedback may change the visible layer, but it must not rewrite the underlying environment or evaluation outcome.

## Bounded completeness

ChemWorld targets structural completeness of the experimental-interaction chain across selected physical-chemistry archetypes. Chemical coverage and numerical fidelity remain bounded and declared, not exhaustive.

Next: [API Reference](reference.md) · [Benchmark Design](benchmark-design.md) · [Limitations](limitations.md)
