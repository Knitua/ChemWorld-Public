# Causal Worlds

> **ChemWorld is not defined by having many tasks. Its distinctive capability is running the same public task under different, auditable hidden rules.**

A high score in one fixed simulator cannot tell us whether an agent learned to experiment or merely learned that simulator. ChemWorld can change a registered rate, constitutive relation or apparatus boundary while keeping the public task, action language and instrument semantics fixed.

## World, task, scenario and seed

| Concept | Meaning |
| --- | --- |
| World | Hidden causal rules: kinetics, phase behavior, equipment and observation generation |
| Task | Public experimental problem, permissions, budget and success criteria |
| Scenario | A task–world composition with initial state and declared intervention condition |
| Seed | Deterministic index used to reconstruct an instance |

Changing a seed usually changes instance randomness, not causal structure. Multi-seed robustness is therefore not the same as adaptation to a changed world.

## Stable public contract

Across a controlled fork, the agent sees the same task goal, typed operations and instrument meanings. It does not receive the world label or private mechanism parameters. If adaptation occurs, it must be visible through selected measurements, revised decisions and downstream outcomes.

## A minimal example

Under the same reaction task, a temperature increase might mainly accelerate the desired route, amplify a competing route or expose an equipment limitation. A fixed recipe cannot distinguish those explanations. An experimental agent must choose evidence that can.

## What Public v0.4 qualifies

The frozen release contains six matched parent/child pairs and 24 traces. Each pair changes one registered private component, executes the declared fixed public policy and passes exact replay audit. This establishes controlled software-world interventions within the declared model domain; it does not establish that a candidate agent can identify every change or transfer to a physical system.

For implementation detail, see the [world composition contract](world-composition-contract.md), [composition coverage](world-composition-coverage.md) and [controlled-world protocol](https://github.com/Knitua/ChemWorld-Public/blob/main/protocols/controlled-world-forks.md).

Next: [System Model](architecture.md) · [Showcase Worlds](worlds.md) · [Real-world Bridge](real-world-bridge.md)
