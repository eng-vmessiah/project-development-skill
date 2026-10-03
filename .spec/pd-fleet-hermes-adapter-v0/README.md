# PD Fleet → Hermes Adapter v0

**Status:** `passed_local_fake_only` / `NOT_READY_RUNTIME`
**Scope change:** autorizada por Vitor em 2026-07-28
**Owner/orchestrator:** `isis`
**Baseline:** working tree after `pd-fleet-scope-alignment` Gate B (`LOCAL_VERIFIED`)
**External effects:** disabled

## Purpose

Define, review, and locally verify a narrow runtime-adapter seam between a Fleet envelope and a controlled fake Hermes delegate. This wave is contract-first and fake-only; its final evidence does not authorize a real Hermes adapter or provider execution.

## Non-goals

- no live `delegate_task` call;
- no provider/model activation;
- no credentials, network, cron, subprocess, or gateway changes;
- no production sandbox or worker pool;
- no OMH integration;
- no merge, push, release, deploy, or restart;
- no claim of Hermes runtime readiness.

## Required decision gates

1. **G0 — Contract discovery:** canonical identity/lifecycle, ownership, bounds, redaction, and no-dispatch rules recorded.
2. **G1 — Independent contract review:** no HIGH/BLOCKER; unresolved ambiguity is `HOLD`, not implementation permission.
3. **G2 — Fake implementation authorization:** explicit checkpoint after G1; fake runtime must prove `dispatch_count == 0`.
4. **G3 — Local fake verification:** schema/contract, lifecycle, replay, cancellation, cleanup, and no-dispatch evidence green.

The final state is **`passed_local_fake_only` / `NOT_READY_RUNTIME`**: the fake-only implementation, vertical evidence, independent harness, closure regressions, and fresh reviews passed. This does not authorize Hermes/provider execution or imply runtime/release readiness.
