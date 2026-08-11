# Evidence guide

The v0.2.0 release retains exactly four final evidence groups. Readable Markdown files summarize
the three longer reports; compressed JSON files preserve the complete public scientific payload.

| Artifact | Role | Public protocol |
| --- | --- | --- |
| `reports/composition-qualification.md` | Full-census construction summary | `protocols/composition-qualification.md` |
| `reports/composition-qualification.json.gz` | Complete composition and replay report | `protocols/composition-qualification.md` |
| `reports/deterministic-use-cases.md` | Eight lifecycle, resource and replay cases | `protocols/deterministic-use-cases.md` |
| `reports/deterministic-use-cases.json.gz` | Complete submitted-action and receipt records | `protocols/deterministic-use-cases.md` |
| `reports/controlled-world-forks.json.gz` | Six matched private-law interventions and 24 traces | `protocols/controlled-world-forks.md` |
| `reports/agent-instrument-use.md` | Independent-agent integration summary | `protocols/agent-instrument-use.md` |
| `reports/agent-instrument-use.json.gz` | Complete sanitized agent lifecycle and replay record | `protocols/agent-instrument-use.md` |

Every compressed report includes a `release_sanitization` receipt. The receipt records the
original compressed and canonical report hashes, sanitizer version, public protocol binding,
removed-metadata summary digest and deterministic serialization settings. Internal source
bindings and provider session identifiers are not retained.

Run `python scripts/verify_release.py` to validate all report hashes, denominators, failure records
and replay outcomes without network access.
