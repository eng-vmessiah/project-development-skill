# PD Fleet → Hermes Adapter v0 — G3 Verification

**Decision:** `passed_local_fake_only` / `NOT_READY_RUNTIME`
**Scope:** `local_fake_only`
**External effects:** disabled

## Fresh commands

| Gate | Command | Result |
|---|---|---|
| Full suite | `pytest -q` | `1104 passed` |
| Focused adapter/contract/docs/closure | `pytest -q tests/fleet/test_g3_closure_debts.py tests/fleet/test_v2_fake_adapter.py tests/fleet/test_v2_contracts.py tests/fleet/test_v2_doc_paths.py` | `149 passed` |
| Fixture harness | `python scripts/pd_fleet/fixture_harness.py --manifest .spec/pd-fleet-hermes-adapter-v0/contracts/manifest.json` | `25/25 valid` |
| Vertical runner | `PYTHONPATH=scripts/pd_fleet python scripts/pd_fleet/run_fake_vertical.py` | `4 cases; local_fake_only=true; dispatch=[1,0,1,1]` |
| Compile | `python -m compileall -q scripts/pd_fleet` | `PASS` |
| Diff check | `git diff --check` | `PASS` |
| Documentation paths | `python scripts/pd_fleet/v2_doc_paths.py .` | `violation_count=0` |
| AST parse | `fake_adapter.py`, `fixture_harness.py`, `run_fake_vertical.py` | `PASS` |
| Closure regression | `pytest -q tests/fleet/test_g3_closure_debts.py` | `3 passed` |
| Module runner | `python -m scripts.pd_fleet.run_fake_vertical` | `4 cases; local_fake_only=true; dispatch=[1,0,1,1]` |

## Vertical cases

- `happy_vertical`: `prepare → execute → observe → handoff → cleanup`, dispatch count `1`, terminal status preserved, cleanup `cleaned`.
- `confirmed_cancel`: `prepare → cancel(confirm) → cleanup`, dispatch count `0`, cancellation confirmation present, cleanup `cleaned`.
- `cleanup_failure_retry`: `prepare → execute → cleanup_failed → cleanup`, dispatch count `1`, terminal status preserved, final cleanup `cleaned`.
- `timed_out_cleanup`: `prepare → execute(timed_out) → cleanup`, dispatch count `1`, timeout status preserved through cleanup.

The runner independently validates emitted results against `contracts/result-schema.json`, bounds its report below 8192 UTF-8 bytes, and emits only bounded evidence references and statuses.

## Fixture harness

`scripts/pd_fleet/fixture_harness.py` is implementation-independent: it does not import `FakeAgentRuntime`. It validates the manifest's 25 listed fixtures using local Draft 2020-12 schemas and separates:

- request projections, with explicit synthetic placeholders for scenario fixtures that intentionally omit operation fields;
- result fixtures;
- scenario-only metadata.

It performs no network schema resolution and emits no absolute local paths in its report.

## G3 closure

The two previous LOW debts are closed in the current tree:

- the offline harness now opens manifest, schemas, and fixtures through descriptor-pinned reads with `O_NOFOLLOW`, regular-file checks, and component-wise bundle confinement;
- the vertical runner now supports both the documented direct-script invocation and package/module execution, with byte-identical reports.

The closure regression tests cover both boundaries. No residual LOW debt remains for the local fake-only G3 gate.

This closure does not authorize Hermes/provider readiness, external-effect safety outside the inspected fake boundary, human approval, merge readiness, deployment, release, or runtime readiness. A fake-only result is never evidence of live provider quality.