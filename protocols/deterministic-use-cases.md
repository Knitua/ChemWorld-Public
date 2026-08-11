# Deterministic lifecycle and recovery protocol

Status: **frozen before execution**

## Question

Can diverse public workflows use one transaction, resource, lifecycle and exact-replay contract
without process-specific exception semantics?

## Frozen cases

Eight complete cases cover reaction-to-crystallization, resource-limited characterization,
planned failure and recovery, continuous flow, electrochemistry, distillation, partition and a
second crystallization world. Together they contain 89 submitted actions, 88 expected commits,
one expected runtime-precondition rollback and eight final assays.

## Pass conditions

- All eight lifecycles close with exactly one committed final assay.
- The planned first-step failure rolls back without changing committed physical state,
  observation random-number state or ghost state; its declared attempt cost is retained.
- The remaining 18 actions in the recovery case and every action in the other seven cases commit.
- Resources reconcile step by step and at lifecycle closeout.
- Public outputs expose no evaluator-owned private state.
- All eight complete submitted-action traces replay exactly.

The cases qualify shared instrument and execution semantics. They are examples rather than an
agent benchmark or an exhaustive task-space claim.
