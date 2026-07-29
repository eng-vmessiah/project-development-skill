# PD Fleet → Hermes Real Adapter v1 — Discovery Plan

> **For Hermes:** This plan is discovery/design only. Do not implement runtime integration or activate external capabilities.

**Goal:** Produce a reviewed, implementation-ready design for a real Fleet-to-Hermes adapter without executing Hermes, providers, network, credentials, subprocesses, or production infrastructure.

**Architecture:** Preserve the v0 bounded lifecycle and lineage contract. Discover the actual Hermes-owned seam, define a narrow translation boundary, and keep provider policy, credentials, sandboxing, and external effects outside Fleet unless a later scope explicitly authorizes them.

**Tech Stack:** Repository documentation and read-only source inspection; existing Fleet Python contracts/tests; no new runtime dependency in discovery.

---

## Discovery gates

### D0.1 — Inventory actual Hermes integration surfaces

**Read-only files/areas:** repository Hermes references, `scripts/pd_fleet/runtime_adapter.py`, `scripts/pd_fleet/runtime_adapters.py`, `scripts/pd_fleet/provider_routing.py`, `scripts/pd_fleet/provider_dispatch.py`, provider readiness docs, and Hermes configuration/API documentation available in the environment.

**Output:** `DISCOVERY.md` with fact/evidence references, supported seams, forbidden seams, and stale-document findings.

**Gate:** no implementation proposal based on an unverified or invented Hermes API.

### D0.2 — Define the bridge contract

**Output:** versioned design for Fleet request → Hermes invocation → normalized result/event/handoff/cleanup, including lineage, ownership, idempotency, timeout, cancellation, redaction, bounds, and error taxonomy.

**Required distinction:** Fleet remains authoritative for Fleet lifecycle; Hermes remains authoritative for concrete runtime/session state.

**Gate:** contract review returns `PASS` or `HOLD`; unresolved ambiguity blocks implementation.

### D0.3 — Define capability and effect boundaries

**Output:** explicit matrix for provider selection, credentials, network, filesystem/workspace, subprocess, gateway, sandbox, and external writes.

**Required evidence:** default-deny behavior, capability binding to current run/scope, audit/provenance requirements, and human approval points.

**Gate:** security/quality review identifies no unowned HIGH/BLOCKER boundary.

### D0.4 — Define injected test and canary strategy

**Output:** test design using injected Hermes/delegate doubles first, then a separately approved local canary. Include success, failure, timeout, cancellation, retry, restart/replay, cleanup, malformed result, provider unavailable, and capability denial.

**Gate:** test plan proves no live effect during implementation tests and identifies the exact transition to any later live canary authorization.

### D0.5 — Discovery decision packet

**Files:** `DISCOVERY.md`, `STATE.md`, `VERIFICATION.md` in this scope.

**Output:** reviewed design packet plus one of:

- `DESIGN_READY_FOR_EXPLICIT_IMPLEMENTATION_AUTHORIZATION`;
- `HOLD_UNRESOLVED`;
- `CANCELLED/SUPERSEDED`.

This decision does not itself authorize implementation, provider access, credentials, network, or live dispatch.

## Verification

- read-only inventory has source/file evidence;
- no production/runtime files modified during discovery;
- facts, decisions, hypotheses, risks, and open questions are separated;
- spec/compliance review and security/quality review are fresh and independent;
- documentation/path checker and `git diff --check` pass;
- all external capabilities remain disabled.
