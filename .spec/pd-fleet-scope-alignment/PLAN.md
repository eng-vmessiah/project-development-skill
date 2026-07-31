# PD/Fleet Scope Alignment — Implementation Plan

> **For Hermes:** Execute this plan with fresh subagents, TDD for code tasks, independent spec-compliance review followed by code-quality review, and parent-workspace verification after every task.

**Goal:** Align PD/Fleet/Hermes/OMH boundaries, then close only the local Fleet correctness findings H04–H06.

**Architecture:** PD remains the development workflow and decision layer. Fleet remains an optional local coordination protocol/engine. Hermes remains the runtime host, including `delegate_task` and cron. OMH is reference-only. No live runtime or production infrastructure is part of this plan.

**Baseline:** clean `release/pd-v2-hardening` at `c14b333`.

---

## Execution model

Each implementation task follows:

1. fresh subagent receives only its bounded task context;
2. RED test first for code changes;
3. GREEN minimal implementation;
4. focused tests and required checks;
5. parent verifies files, diff, and claims;
6. fresh spec-compliance review;
7. fresh quality/security review;
8. task state advances only after both reviews pass.

A parallel wave is valid only when tasks have disjoint write ownership and no dependency on another task's output.

## Wave 0 — Scope and plan alignment (serial)

### Task S0.1 — Establish scope control plane

**Files:** `.spec/pd-fleet-scope-alignment/SPEC.md`, `CONTEXT.md`, `STATE.md`, `README.md`.

**Objective:** Record the approved boundaries, non-goals, baseline, external-effect policy, and execution model.

**Acceptance:** All requirements/non-goals are explicit; baseline is recorded; no production or OMH-live claim appears.

**Verification:** JSON/state validation as applicable; `git diff --check`.

### Task S0.2 — Update architecture and roadmap

**Files:** `docs/ARCHITECTURE.md`, `ROADMAP.md`.

**Objective:** Describe PD Core, PD Fleet, Hermes Runtime Host, runtime adapters, and OMH reference-only status.

**Dependencies:** S0.1.

**Acceptance:** Documents no longer imply that Fleet owns cron, provider execution, production sandbox, or live dispatch. Future runtime work is explicitly deferred.

**Verification:** `git diff --check`; `python scripts/pd_fleet/v2_doc_paths.py .`.

### Task S0.3 — Add directional architecture note to Fleet planning docs

**Files:** `docs/PD-AS-IS-TO-BE.md`, `docs/PD-FLEET-ORCHESTRATION-PLAN.md`.

**Objective:** Preserve the historical evolution while correcting the target boundary and local-only success criteria.

**Dependencies:** S0.1.

**Acceptance:** Existing history is not rewritten as if production existed; the future Hermes adapter is a seam, not a live implementation; cron and OMH runtime integration are excluded.

**Verification:** `git diff --check`; documentation checker.

### Task S0.4 — Reclassify GRILL-001 findings

**Files:** `.spec/pd-fleet-scope-alignment/RESEARCH.md`, `artifacts/v2/GRILL-001-findings.json` only if schema-compatible and explicitly approved by parent.

**Objective:** Map each finding to `retain-local`, `defer-runtime`, `superseded-by-scope`, or `evidence-later` without changing historical evidence dishonestly.

**Dependencies:** S0.2, S0.3.

**Acceptance:** H04/H05/H06 are retained local correctness work; sandbox/provider/deployment findings are deferred or scoped as future runtime concerns; historical counts and decisions remain intact.

**Verification:** independent review; JSON parse; no secret values; diff check.

### Gate A — Scope approval

The parent verifies all scope documents and dispatches two parallel read-only reviewers:

- architecture boundary reviewer;
- plan/findings reconciliation reviewer.

Advance only if both report no HIGH/BLOCKER in the revised scope. This is not release approval.

---

## Wave 1 — Independent local correctness work

### Task H04 — Atomic dependency readiness and claim

**Files (closed ownership):** `scripts/pd_fleet/scheduler.py`, `scripts/pd_fleet/run_store.py`, `scripts/pd_fleet/orchestrator.py` only as required; `tests/fleet/test_v2_scheduler.py`, `tests/fleet/test_v2_run_store.py`, `tests/fleet/test_v2_concurrency_integration.py`. Do not edit `gates.py`, `tests/fleet/test_v2_human_gate.py`, or shared human-gate tests in this parallel task.

**Objective:** Ensure dependency readiness is revalidated in the same locked claim path so a dependency invalidated after `ready_ids()` cannot be claimed.

**Dependencies:** Gate A.

**TDD:** Add RED regression that mutates/invalidate a dependency between readiness observation and claim; prove no invalid task is leased and state remains intact. Implement the smallest atomic/revalidation change. Run focused tests, then scheduler/store/orchestrator regressions.

**Acceptance:** No stale readiness can produce a lease; claim capacity and path ownership remain bounded; no duplicate claim; no unintended mutation on rejection.

**Verification:**

```bash
pytest -q tests/fleet/test_v2_scheduler.py tests/fleet/test_v2_run_store.py tests/fleet/test_v2_concurrency_integration.py
```

### Task H06 — Scope/run-bound HumanVerificationGate

**Files (closed ownership):** `scripts/pd_fleet/gates.py`; `tests/fleet/test_v2_human_gate.py`. Do not edit `orchestrator.py`, scheduler/store files, or shared orchestrator-governance tests in this parallel task; integration admission coverage is reserved for H05.

**Objective:** Require the current operation's expected run and canonical scope when evaluating human authorization; mismatch fails closed.

**Dependencies:** Gate A. Can run in parallel with H04 if parent confirms disjoint ownership.

**TDD:** Add RED cases for a gate recorded for another run/scope, missing expected inputs, stale digest, and freshness mismatch. Implement explicit expected run/scope evaluation without auto-approval or authentication claims.

**Acceptance:** A valid-looking approval for another run or scope cannot authorize the current operation; missing expected context fails closed; existing valid gate behavior remains compatible.

**Verification:**

```bash
pytest -q tests/fleet/test_v2_human_gate.py tests/fleet/test_v2_orchestrator_governance_gates.py
```

### Wave 1 review

After H04 and H06 implementations, run independent spec review and quality/security review per task. Reviewers must inspect the actual diff and tests, not trust summaries.

---

## Wave 2 — Dependent ownership/fencing hardening

### Task H05 — Enforce human-required gate admission path

**Files (closed ownership):** `scripts/pd_fleet/orchestrator.py`, `scripts/pd_fleet/gates.py` only as required; `tests/fleet/test_v2_orchestrator_governance_gates.py`, `tests/fleet/test_v2_human_gate.py`. This task is the only task allowed to edit shared admission/gate integration paths after H04 and H06 reviews.

**Objective:** Prevent an ordinary `GateResult` from bypassing `HumanVerificationGate` when the operation requires human authorization, while preserving the distinction between execution gates and PD decision gates.

**Dependencies:** Gate A, successful review of H04, and successful review of H06. H05 is strictly sequential after both H04 and H06; no conditional shortcut is allowed.

**TDD:** Add RED regression where a passed ordinary gate with owner/decision/evidence is supplied for a human-required operation; prove dispatch/admission is blocked without a valid current human gate. Add positive case with matching run/scope/digest/freshness.

**Acceptance:** Human-required operations cannot be authorized by ordinary gate data; no autoapprove path; errors are stable and non-sensitive; local simulated execution remains available for non-human-required gates.

**Verification:**

```bash
pytest -q tests/fleet/test_v2_orchestrator_governance_gates.py tests/fleet/test_v2_human_gate.py
```

### Wave 2 review

Fresh spec-compliance review, then quality/security review. If findings affect H04/H06 contracts, return the affected task to `revise` and rerun its reviews.

---

## Wave 3 — Local closure and evidence

### Task V3.1 — Reconcile documentation and evidence

**Files:** `.spec/pd-fleet-scope-alignment/VERIFICATION.md`, `.spec/pd-fleet-scope-alignment/STATE.md`, optional `artifacts/v2/` resolution artifacts only when generated from fresh commands.

**Objective:** Record exact local evidence and distinguish implementation-complete, verification-complete, and delivery-ready states.

**Dependencies:** H04, H05, H06 and reviews.

**Verification commands:**

```bash
pytest -q
python -m compileall scripts/pd_fleet
python scripts/pd_fleet/v2_doc_paths.py .
git diff --check
python examples/pd-fleet/run_local.py --plan examples/pd-fleet/plan.yaml --output /tmp/pd-fleet-scope-alignment
```

**Acceptance:** Fresh evidence is recorded; no provider/network/subprocess claim is made; final decision is `LOCAL_VERIFIED`, `PARTIAL`, or `BLOCKED`.

### Task V3.2 — Final integration review

**Files:** read-only review of all changed files.

**Objective:** Detect cross-task inconsistencies, scope creep, stale documentation, missing tests, and accidental runtime activation.

**Dependencies:** V3.1.

**Acceptance:** Reviewer explicitly checks PD/Fleet/Hermes boundaries, H04/H05/H06 interaction, V1 compatibility, no-dispatch behavior, malformed inputs, and human-gate semantics.

### Gate B — Local closure

Required:

- focused tests green;
- full suite and compile green;
- documentation checker green;
- working-tree inventory verified;
- no HIGH/BLOCKER from final review;
- status remains non-production and no G6 release approval is inferred.

---

## Wave 4 — LOW review-debt remediation (authorized continuation)

This wave is a bounded continuation of the local plan. It does not reopen runtime, sandbox, provider, Hermes, OMH, deployment, or release scope.

### Task R04 — Strengthen H04 regression evidence

**Files (closed ownership):** `tests/fleet/test_v2_scheduler.py` only.

**Objective:** Reduce coupling to private mutation/monkeypatching where practical and assert complete state invariance after stale dependency rejection, including generation/checksum/timestamp or the repository's canonical equivalent.

**Dependencies:** Gate B partial; H04 reviews complete.

**Acceptance:** The adversarial stale-readiness regression remains deterministic, proves no lease/attempt, and verifies the complete persisted state remains unchanged except for the intentionally injected dependency invalidation.

**Verification:** focused scheduler/store/concurrency tests; `git diff --check`.

### Task R05 — Strengthen H05 admission evidence

**Files (closed ownership):** `tests/fleet/test_v2_orchestrator_governance_gates.py` only unless a test fixture requires an explicitly justified adjacent test path. Do not modify production code unless a new RED test demonstrates an actual defect.

**Objective:** Add (a) a complete admission/dispatcher assertion proving a human-required operation does not dispatch with an invalid/missing human gate, and (b) hostile custom `Mapping` coverage through the admission boundary, proving fail-closed behavior without an exception escaping.

**Dependencies:** Gate B partial; H05 reviews complete. Can run in parallel with R04 because write ownership is disjoint.

**Acceptance:** No human-required operation reaches its dispatcher without a valid current human gate; hostile mappings fail closed; existing automatic smoke/evidence gate behavior remains green.

**Verification:** governance + human-gate tests; relevant Fleet regressions; `git diff --check`.

### Wave 4 review

After R04 and R05, run fresh spec-compliance and quality/security reviews. Update `VERIFICATION.md` and `STATE.md` with the resulting debt classification. This wave may close as `LOCAL_VERIFIED` only if all acceptance criteria and reviews pass; it still does not authorize production or release.

---

## Wave 5 — Remove H04 private test seam (authorized continuation)

This wave is limited to a public, owner/generation-checked task-status mutation API and its regression coverage. It does not alter scheduler semantics, production runtime boundaries, providers, Hermes integration, deployment, or release scope.

### Task R06 — Public task-status invalidation seam

**Files (closed ownership):** `scripts/pd_fleet/run_store.py`, `tests/fleet/test_v2_scheduler.py`, and the directly corresponding run-store test file only if needed for the public API contract.

**Objective:** Expose a narrow atomic `update_task_status` operation for externally observed task invalidation. Replace the R04 test's direct `_mutate` use with this public API while preserving the deterministic between-readiness-and-claim injection.

**Acceptance:** The API validates task/run ownership and status, performs one sealed mutation under the store lock, fences any active lease without creating or changing attempt counts, and rejects replay claims for all terminal task statuses. Existing scheduler/store behavior remains unchanged.

**Verification:** RED/GREEN public API tests; scheduler/store/concurrency regressions; full suite; compileall; diff check; independent spec and quality reviews.

---

## Deferred follow-up, not part of this execution

1. `HermesDelegateAdapter`: Fleet envelope → Hermes `delegate_task` → normalized `AgentReport`.
2. Integration tests using a controlled fake delegate, with no live provider.
3. Any provider/runtime adapter activation.
4. Strong sandbox, deployment, shared persistence, multi-host workers, operational observability, canary, rollback, and runbook.
5. OMH adapter or runtime integration; OMH remains learning/reference-only unless separately approved.
