# ChemWorld

ChemWorld is a programmable environment for controlled and replayable agent experiments in
chemical worlds. Version `0.2.0` is a stable software-and-evidence release built from the frozen
public snapshot `9df2783`; it intentionally does not incorporate the ongoing Work II development
line.

The runtime composes reaction, thermal, phase, separation, crystallization, distillation,
continuous-flow, electrochemical and observation components behind one typed experimental
contract. It supports transactional execution, explicit resource accounting, exact replay and
controlled single-law counterfactual worlds.

## Release scope

This repository contains:

- the complete frozen, installable `src/chemworld` runtime and its public API;
- stable public configuration, including `configs/public_dev.json` as a data-split definition;
- public protocols, examples, focused tests and offline verification tooling;
- four final, deterministically sanitized evidence reports: composition qualification,
  deterministic use cases, controlled world forks and agent instrument use.

It deliberately excludes manuscript files, PDFs, figures, source packages, planning notes,
TODOs, workstream records, draft/interim/pilot outputs, raw provider responses, provider session
identifiers, private evaluator configuration, credentials and all Work II artifacts.

## Verified evidence

- 64/64 registered task–world units and 1,786/1,786 reference recipes completed.
- 52/52 coverage-generated compositions completed, including 8/8 frozen non-reference
  reaction–distillation worlds.
- 32/32 module probes, 7/7 interface paths, 7/7 invalid declarations and 192/192 invalid-action
  probes produced their registered outcomes.
- Eight deterministic lifecycles checked all 89 submitted actions: 88 committed and one planned
  rollback was preserved in exact replay.
- Six controlled parent–child world pairs produced 24 provider-free traces.
- One independent agent completed a 15-action lifecycle through the public instrument interface.

These are finite software-model qualification results. They do not establish universal chemical
fidelity, real-laboratory transfer or general agent intelligence.

## Install and verify

ChemWorld supports Python 3.11 and 3.12.

```bash
git clone https://github.com/sunyrain/ChemWorld-Public.git
cd ChemWorld-Public
python -m pip install -e ".[dev]"
python scripts/verify_release.py
```

Basic CLI and example checks:

```bash
chemworld --help
python examples/demo_manual_event_sequence.py
python -m pytest -q
```

`scripts/verify_release.py` works offline. It checks the exact Git-tracked file set and hashes,
the four evidence sanitization receipts, denominators, failures and replay results, the public
release boundary, and the clean single-commit history.

## Repository layout

| Path | Contents |
| --- | --- |
| `src/chemworld/` | Frozen executable environment and public agent interface |
| `configs/` | Stable runtime and public split configuration |
| `protocols/` | Frozen public experiment protocols |
| `evidence/reports/` | Final readable summaries and compressed sanitized reports |
| `examples/` | Runnable API and world-authoring examples |
| `tests/` | Focused runtime and release-boundary tests |
| `release/manifest.json` | Exact file hashes, provenance, exclusions and evidence receipts |
| `scripts/verify_release.py` | Offline fail-closed release verification |

## Evidence provenance

Each compressed report retains actions, observations, numerical results, resource and transaction
receipts, failures, exact denominators and replay outcomes. Its embedded sanitization receipt binds
the original report SHA-256, the sanitizer version, the public protocol, and a digest plus category
counts for removed metadata. JSON serialization is canonical and gzip uses `mtime=0`, so repeated
sanitization is byte-for-byte reproducible.

See [evidence/README.md](evidence/README.md) for the report map and [CITATION.cff](CITATION.cff)
for machine-readable citation metadata.

## License

The software and release tooling are available under the [MIT License](LICENSE).
