# Why ChemWorld

> **ChemWorld gives experimental intelligence its own world engine.**

Many scientific benchmarks ask a model to retrieve, predict or explain from a fixed input. Real experimentation is different: evidence is incomplete, measurements have consequences, operations can fail, and the next useful action depends on what just happened.

ChemWorld turns that interaction into a first-class research object. An agent receives a public task contract and a partially observed laboratory. It must choose operations and instruments, respect resources and preconditions, interpret public signals, recover when a plan breaks, and deliberately close the experiment.

## The missing middle

| Knowledge benchmark | ChemWorld | Physical laboratory |
| --- | --- | --- |
| Evidence is already supplied | The agent must acquire evidence | Evidence is acquired through real equipment |
| One answer is scored | A complete trajectory is audited | Procedures and measurements carry real risk |
| World rules are usually fixed | Hidden rules can change under controlled forks | Laws are fixed, systems and equipment vary |

ChemWorld occupies the middle: rich enough to study experimental decisions, but deterministic and inspectable enough to replay them exactly.

## The central research program

1. **Worlds:** compose bounded chemical-process models behind stable public interfaces.
2. **Interaction:** make measurements, failures, resources and lifecycle choices explicit.
3. **Agents:** compare how policies acquire evidence and adapt, not only what endpoint they reach.
4. **Evaluation:** separate outcomes, constraints, resources, adaptation and autonomy.
5. **Bridge:** test transfer through independent backends, datasets and narrow approved physical systems.

## What success would mean

The goal is not a chatbot that recites chemistry and not a universal numerical simulator. The goal is an auditable environment where experimental competence becomes measurable: choosing informative interventions, updating after evidence, recovering from failure and adapting when an old local model stops working.

## Public v0.4 boundary

Public v0.4 provides 15 typed tasks, qualified world compositions, provider-free interactive agents, controlled single-law forks, exact replay and one complete sanitized agent lifecycle. It does **not** publish a cross-method Agent ranking, private confirmation set, universal chemical-fidelity claim or physical-lab transfer result.

Continue with [Experimental Intelligence](experimental-intelligence.md), [Causal Worlds](causal-worlds.md) or the [System Model](architecture.md).
