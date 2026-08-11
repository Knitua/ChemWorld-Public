# Independent-agent integration protocol

Status: **frozen before the passing execution**

## Question

Can one persistent operation-level agent use only the public experimental contract to close a
complete lifecycle in a coverage-generated reaction–thermal–distillation–observation world,
while preserving resource accounting, the public/private boundary and exact replay?

## Experimental unit

The sole unit is one complete agent lifecycle in the first protocol-frozen non-reference
reaction–distillation composition. The world, seed and generation order were fixed before the
provider session. No alternative world was selected after observing an outcome.

## Public interface

The agent receives the public task card, typed operation schemas, available instruments,
resource ledger, observations, termination rule and final-assay interface. It does not receive
private chemical laws, material identities, evaluator state or the deterministic reference
trajectory. Every physical operation is submitted through the same host-owned instrument
interface used by deterministic cases.

## Pass conditions

- Exactly one persistent provider session controls the lifecycle.
- Between 1 and 16 typed actions are submitted; all must commit.
- The agent explicitly terminates and performs exactly one final assay.
- No host fallback, action repair, automatic termination or automatic assay is permitted.
- Process time, material, sample and instrument ledgers reconcile within their frozen limits.
- No evaluator-owned private field is exposed through the public record.
- The full submitted-action trace replays exactly with zero numerical mismatch.

The endpoint is descriptive. This protocol demonstrates interface compatibility and auditable
execution, not comparative model performance, general intelligence or physical-laboratory
validity. Raw provider responses, credentials and private reasoning are excluded from release.
