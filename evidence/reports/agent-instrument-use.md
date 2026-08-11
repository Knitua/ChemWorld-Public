# Independent-agent instrument use

Status: **PASSED**

## Complete census

| Quantity | Observed | Required |
| --- | ---: | ---: |
| Lifecycles | 1 | 1 |
| Submitted actions | 15 | 1--16 |
| Trajectory records | 15 | submitted actions |
| Committed actions | 15 | submitted actions |
| Rollbacks | 0 | 0 |
| Committed terminate | 1 | >=1 |
| Committed final assay | 1 | 1 |
| Provider sessions/model calls | 1/1 | 1/1 |
| MCP step calls | 15 | submitted actions |
| Public/private leakage findings | 0 | 0 |

All submitted actions are inspected; sampling is not used as a pass gate.

## Closure and replay

- Lifecycle closed: `true`.
- Environment resources reconciled: `true`.
- Declared process-time budget: `8158.454222464699` / `10440.0` s; passed `true`.
- Declared sample budget: `0.0008500000000000001` / `0.001` L.
- Exact replay: `true`; max absolute error `0.0`.
- Input/output tokens: `493092` / `2973`.
- Per-run USD price: unavailable for cached ChatGPT subscription login; no measured zero is reported.

## Prerequisite controlled-fork evidence

- Frozen fork pairs/traces/provider calls: `6` / `24` / `0`.

## Failures

None.

## Claim boundary

- One complete-agent virtual-instrument usability demonstration only.
- The endpoint score is descriptive and is not a performance threshold or ranking.
- No physical-laboratory validity or general-agent claim is made.
