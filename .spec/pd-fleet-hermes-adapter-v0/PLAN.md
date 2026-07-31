# PD Fleet → Hermes Adapter v0 — Plan

> **For Hermes:** Execute only after G1 contract review and explicit G2 authorization. Use fresh subagents per task, with spec-compliance review followed by quality/security review.

**Goal:** Define and locally verify a fake-only Fleet → Hermes runtime seam without activating Hermes, providers, network, subprocesses, credentials, or production infrastructure.

**Architecture:** Contract-first adapter boundary around the canonical Mission → MissionRun → Lane → Attempt → SessionHandle lineage. The fake implementation is in-memory and deterministic; `prepare` is non-dispatching, `execute` is the only fake dispatch boundary, and all public data is bounded/redacted.

**Tech Stack:** Existing Python Fleet V2 modules, pytest, standard library only unless repository inspection proves an existing dependency is required.

---

## Wave 0 — Contract discovery

### Task G0.1 — Inventory existing seams

**Files:** read-only inspection of `scripts/pd_fleet/`, `tests/fleet/`, `.spec/pd-fleet-scope-alignment/`, and relevant docs.

**Output:** update `CONTEXT.md` with actual module ownership, existing report/event shapes, and resolved unknowns.

**Verification:** exact file inventory, `pytest -q`, no edits to production code.

### Task G0.2 — Define parseable contract fixtures

**Files:** to be selected after G0.1; likely `.spec/pd-fleet-hermes-adapter-v0/contracts/` only.

**TDD:** create positive and negative fixtures for lineage, lifecycle, operation inputs, bounded outputs, redaction, and idempotency conflict.

**Gate:** no implementation until fixture vocabulary is independently reviewed.

## Gate G1 — Independent contract review

A read-only reviewer must inspect SPEC, CONTEXT, PLAN, fixtures, and repository seams. Required verdict: `PASS` or `HOLD`, with no HIGH/BLOCKER. A self-report is not evidence.

## Gate G2 — Fake implementation authorization

After G1 PASS, record explicit authorization in `STATE.md` before changing production/test runtime code.

---

## Wave 1 — Fake runtime contract

### Task F1.1 — Add fake lifecycle model

**Files:** a new bounded fake adapter module and owned tests, exact paths decided by G0.1.

**Requirements:** implement prepare/execute/observe/cancel/handoff with no external calls, strict lifecycle transitions, lineage checks, bounded result categories, and opaque handles.

**TDD:** RED for each operation, then minimal GREEN implementation.

### Task F1.2 — Add replay and concurrency invariants

**Requirements:** same-key replay, fingerprint conflict, one cancellation winner, monotonic events, read-only observe, and no duplicate fake dispatch.

### Task F1.3 — Add cleanup and redaction invariants

**Requirements:** cleanup across all terminal paths, no secret/prompt/native-handle leakage, rejection of oversized/control-character input.

## Wave 1 review

Fresh spec-compliance review, then quality/security review. Any HIGH/BLOCKER returns the affected task to `revise`.

## Wave 2 — Local fake vertical verification

### Task V2.1 — Compose Fleet envelope with fake adapter

Prove one admitted local task flows through lineage, fake lifecycle, bounded result, evidence reference, and cleanup. Label all evidence `local_fake_only`.

### Task V2.2 — Adversarial verification

Run malformed lineage, stale handle, replay conflict, timeout/cancel distinction, cleanup failure/recovery, and forbidden-import/no-dispatch probes.

### Task V2.3 — Documentation and state closure

Update `VERIFICATION.md`, `STATE.md`, and relevant architecture/roadmap pointers with exact fresh commands and results. Do not alter the parent plan's production/release status.

## Gate G3 — Local fake verification

Required: full suite, focused adapter suite, compileall, diff check, documentation checker, no-dispatch evidence, security review PASS, and explicit `local_fake_only` classification.

## Deferred follow-up

A real Hermes adapter or provider lane requires another scope change after G3. It is not implied by fake verification.
