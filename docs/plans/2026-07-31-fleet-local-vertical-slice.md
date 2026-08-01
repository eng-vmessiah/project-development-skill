# Fleet Local Vertical Slice Implementation Plan

> **Scope:** local/simulated Fleet only. Hermes, providers, network, credentials, subprocesses, push, merge and release remain out of scope.

**Goal:** Make `pd v2 run-local` execute a deterministic simulated Fleet task through the existing run store, lifecycle, report and resume path instead of intentionally failing because no validator is injected.

**Architecture:** Reuse the existing `Dispatcher` and its internal `SimulatedAdapter`; do not create a second fake runtime. The CLI supplies `report_v2=True`, so the existing orchestrator validates and persists the simulated report through `FleetRunStore`. External adapters remain denied.

---

### Task 1: Add RED coverage for the local vertical path

**Files:**
- Modify: `tests/fleet/test_v2_cli.py`

**Behavior:** `v2 run-local --provider local` must complete a valid plan, persist a completed report, expose deterministic evidence, and return the persisted completed result on a second invocation.

**Verification:** `pytest -q tests/fleet/test_v2_cli.py` must fail against the current intentional-failure adapter.

### Task 2: Wire the existing simulated dispatcher

**Files:**
- Modify: `scripts/pd.py`

**Implementation:** Instantiate the existing `Dispatcher()` inside `_cmd_v2`; replace the intentional raising adapter with a callback that calls `Dispatcher.dispatch(task, {attempt, report_v2: True})`. Keep `--provider disabled` and all external adapters fail-closed.

**Verification:** Focused CLI tests pass; output contains only canonical bounded local evidence.

### Task 3: Re-run the local vertical and full Fleet gates

**Commands:**
- `pytest -q tests/fleet/test_v2_cli.py`
- `pytest -q tests/fleet`
- `python3 -m compileall -q scripts/pd_fleet scripts/pd.py tests/fleet/test_v2_cli.py`
- `git diff --check`
- `python3 scripts/pd_fleet/v2_doc_paths.py .`

**Acceptance:** local run completes and resumes idempotently; `v2 inspect` projects bounded readiness/status/event evidence read-only; `v2 readiness` returns `ready=true` only for a completed consistent run; external provider remains denied; output names are bounded allowlisted report keys; no Hermes/live claim is introduced.

### Task 4: Independent review and checkpoint

Review the final diff for no external effects, report redaction, persistence/resume correctness and provider denial. Commit locally only after fresh review passes. Update Fleet docs/state with `fleet-local` verified evidence separately from `NOT_READY_HERMES_SEAM`.
