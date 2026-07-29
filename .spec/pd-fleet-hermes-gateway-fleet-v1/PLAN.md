# PD Fleet → Hermes Gateway Fleet Bridge v1 — Discovery Plan

> **For Hermes:** This plan is discovery/design only. Do not implement runtime integration or activate external capabilities.

**Goal:** Produce a reviewed, implementation-ready design for Fleet to observe Hermes sessions through the Hermes Gateway and later distinguish user-owned observation from explicitly Fleet-owned coordination.

**Architecture:** Fleet is a Gateway client/bridge, not a dashboard dependency and not an ACP executor. Hermes owns concrete runtime/session state; Fleet owns coordination state; PD Core owns intent and decision gates.

**Tech Stack:** Read-only Hermes source/docs inspection; existing Fleet Python contracts/tests; injected Gateway protocol doubles; no new runtime dependency in discovery.

---

## Gate G0 — Reconcile current architecture and evidence

**Output:** `DISCOVERY.md` with current facts, historical evidence, stale claims, and source/file references.

**Must verify:** dashboard/desktop/serve relationship; standalone terminal session path; Gateway JSON-RPC/WebSocket methods; event dispatch; channel scope; auth boundary; session identity; state persistence; whether a supported global Fleet subscription exists.

**Gate:** no implementation proposal based on an inferred dashboard-only behavior or invented Gateway API.

## Gate G1 — Define the Gateway → Fleet bridge contract

**Output:** versioned bridge contract for `connect`, `subscribe`, `session.discovered`, `session.info`, `status.update`, `tool.*`, `message.*`, `error`, `heartbeat`, `disconnect`, and `reconnect`.

**Must define:** bounded payloads, unknown-event policy, event version, correlation, normalization, error taxonomy, and provenance references.

**Gate:** contract review identifies the actual supported command/event seam and leaves unresolved fields explicitly open.

## Gate G2 — Define ownership and session/task association

**Output:** ownership matrix and lineage mapping.

**Modes:** `user_owned_session` is read-only by default; `fleet_owned_task` may use the v0 lifecycle only after separate authorization.

**Must define:** owner/profile/workspace binding, attach/detach, duplicate association, foreign-owner denial, orphan/stale session behavior, and no implicit ownership claim.

**Gate:** no path allows Fleet state to masquerade as Hermes runtime authority or user approval.

## Gate G3 — Define cursor, replay, reconnect, and stale semantics

**Output:** event delivery/reconciliation design.

**Must define:** cursor type, ordering, deduplication, gaps, reconnect, snapshot-before-stream, heartbeat TTL, stale/disconnected states, and restart recovery.

**Gate:** an injected test can prove that reconnect does not duplicate completed events or silently convert a gap into success.

## Gate G4 — Define security, capability, and effect boundaries

**Output:** capability matrix and authorization model.

**Default-deny:** prompts, cancellation, provider activation, credentials, filesystem mutation, subprocess control, network exposure, external messaging, and direct database writes.

**Gate:** owner/profile scoping, redaction, bounded output, local authentication, audit/provenance, and fail-closed behavior are assigned to an owner with no unowned HIGH/BLOCKER.

## Gate G5 — Define injected tests and local observer harness

**Output:** test plan and fake Gateway protocol fixture.

**Must cover:** session discovery, metadata normalization, event translation, malformed payload, unknown event, duplicate event, event gap, reconnect, heartbeat expiry, owner mismatch, auth denial, dashboard channel mismatch, and no-live-effect behavior.

**Gate:** all tests use injected doubles/fixtures; no provider, network, credential, subprocess, or live Gateway is required.

## Gate G6 — Implement only after explicit authorization (future)

**Status:** `not_authorized` in this discovery scope.

**Candidate slice:** read-only `FleetGatewayBridge` client with local persistence and observer output. Exact files, dependencies, and commands must be defined only after G0–G5 pass.

**Gate:** separate human authorization names allowed files, runtime process, transport, capabilities, rollback, and verification evidence.

## Gate G7 — Local canary design (future)

**Status:** `not_authorized`.

A local canary may connect only to a deliberately isolated Hermes Gateway fixture or approved local instance. It must have explicit auth, bounded duration, no provider/live-network claim, redaction, rollback, and evidence capture.

## Gate G8 — Closeout and promotion decision

**Output:** `VERIFICATION.md`, reconciled roadmap/docs, decision packet, and explicit status.

Allowed outcomes:

- `DESIGN_READY_FOR_EXPLICIT_IMPLEMENTATION_AUTHORIZATION`;
- `HOLD_UNRESOLVED`;
- `CANCELLED/SUPERSEDED`.

G8 does not authorize production, provider activation, live dispatch, destructive control, or release.

## Verification requirements

- facts, decisions, hypotheses, risks, and open questions separated;
- no runtime/provider/config changes during discovery;
- injected tests and fixtures only;
- docs/path checker passes;
- `git diff --check` passes;
- independent spec/compliance and security/quality review recorded;
- existing v0 fake-only contract remains intact.
