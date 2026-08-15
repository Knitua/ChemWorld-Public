# Experimental Intelligence

> **Answering chemistry questions is not the same as conducting an experiment.**

Experimental intelligence turns knowledge into falsifiable action. An agent must identify what remains unknown, choose operations or measurements that can resolve it, revise explanations when evidence disagrees, and keep moving under safety, cost and time constraints.

## Six capabilities

| Capability | Operational meaning in ChemWorld |
| --- | --- |
| Observe | Distinguish measured public evidence from hidden evaluator state |
| Hypothesize | Maintain tentative explanations without treating them as truth |
| Design | Choose interventions that distinguish competing explanations |
| Operate | Control materials, apparatus and instruments through legal actions |
| Update | Change beliefs and subsequent actions after new evidence |
| Constrain | Trade off outcome, risk, cost, time and sample use |

## Measurement is an action

An instrument call is not a free read of hidden state. It may consume time, money or sample and reveals only the channel allowed by the task contract. A useful policy therefore asks not “what can I measure?” but “which observation could change my next decision?”

## Failure is part of the experiment

ChemWorld records invalid preconditions, uninformative measurements, rejected proposals and incomplete lifecycle choices. Invalid actions do not mutate state or consume the task budget. Recovery—recognizing the problem, choosing a corrective step and avoiding repetition—is itself observable behavior.

## Three levels of mechanism evidence

1. **Declared:** the agent states a belief about a mechanism or change.
2. **Predictive:** that belief predicts an unexecuted intervention.
3. **Actionable:** it changes the next experiment and improves recovery or regret under a fixed budget.

These levels should not be collapsed into one label-accuracy score. Public v0.4 exposes the interaction substrate and controlled-fork evidence needed to design such studies; it does not claim a completed mechanism-understanding ranking.

## Memory at two scales

- **Within one experiment:** materials, conditions, measurements and failures so far.
- **Across experiments:** recipes, outcomes, hypotheses and remaining campaign resources.

Experimental competence is not guessing correctly on the first attempt. It is knowing what to measure after the guess fails.

Next: [Causal Worlds](causal-worlds.md) · [Agent Tracks](agent-tracks.md) · [Benchmark Design](benchmark-design.md)
