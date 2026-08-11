# Deterministic use cases

Status: **PASSED**

## Exact full-census counts

| Quantity | Observed/checked | Denominator/expected |
| --- | ---: | ---: |
| Cases passed | 8 | 8 |
| Submitted actions checked | 89 | 89 |
| Committed actions | 88 | 88 |
| Rolled-back actions | 1 | 1 |
| Committed final assays | 8 | 8 |

All submitted actions are inspected. Sampling is not used as a qualification gate.

## Case results

| Case | Public identity | Seed | Actions | Commit | Rollback | Final assay | Replay | Resource | Leakage | Status |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- | --- | ---: | --- |
| U01 | `reaction-to-crystallization` | 0 | 12/12 | 12 | 0 | 1 | pass | pass | 0 | PASS |
| U02 | `composed-equilibrium-characterization-demo` | 0 | 5/5 | 5 | 0 | 1 | pass | pass | 0 | PASS |
| U03/E01 | `composed-reaction-purification-demo` | 0 | 19/19 | 18 | 1 | 1 | pass | pass | 0 | PASS |
| U06-flow | `flow-reaction-optimization` | 0 | 8/8 | 8 | 0 | 1 | pass | pass | 0 | PASS |
| U06-electro | `electrochemical-conversion` | 0 | 11/11 | 11 | 0 | 1 | pass | pass | 0 | PASS |
| U06-distillation | `reaction-to-distillation` | 0 | 12/12 | 12 | 0 | 1 | pass | pass | 0 | PASS |
| U06-partition | `partition-discovery` | 0 | 10/10 | 10 | 0 | 1 | pass | pass | 0 | PASS |
| U06-crystallization | `reaction-to-crystallization` | 1 | 12/12 | 12 | 0 | 1 | pass | pass | 0 | PASS |

## U03 failure and recovery

Expected rollback step: `1`; observed rollbacks: `1`; subsequent commits: `18/18`; receipt: `passed`.

## Prerequisite public evidence

| Use case | Evidence | Binding SHA verified | Status |
| --- | --- | --- | --- |
| U04 | single-private-component controlled world forks | yes | PASS |
| U05 | frozen unseen generated composition, first generation row | yes | PASS |

Provider calls: `0`.
Public/private leakage findings: `0`.
Missing receipts: `0`.

## Failure classes

None.

## Claim boundary

- Deterministic virtual-instrument use-case qualification only.
- The eight frozen cases are examples, not a benchmark or exhaustive task-space claim.
- No provider was called and no agent-intelligence or physical-laboratory claim is made.
