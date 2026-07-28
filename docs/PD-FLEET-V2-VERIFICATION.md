# Fleet V2 current verification and provenance index

This index records where current V2 claims are defined and verified. It is a
forward-looking index only; historical handoff and research records are not
rewritten here.

## Current source of truth

- Scope and non-goals: [`README.md`](../README.md), Fleet V2 section.
- Current limitations and deferred work: [`ROADMAP.md`](../ROADMAP.md).
- Local example contract: [`examples/pd-fleet/README.md`](../examples/pd-fleet/README.md).
- Installer contract: [`INSTALLER.md`](INSTALLER.md).
- Offline path/link checker: [`v2_doc_paths.py`](../scripts/pd_fleet/v2_doc_paths.py).

## Verification entry points

- `python scripts/pd_fleet/v2_doc_paths.py .` — validates V2 documentation path
  declarations without network or subprocess execution.
- `pytest -q tests/fleet/test_v2_doc_paths.py` — checker regression tests.
- `pytest -q` — repository test suite.

## Provenance boundary

The local simulated runner and checker do not prove provider connectivity,
external dispatch, production readiness, or human G1–G6 approval. Those remain
deferred and must be established by fresh evidence in a separately approved
release decision.
