# B15a Contract Closure & Approval Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Close the B15a planning/approval gap with a reviewed normative packet for the first read-only TUI session observer, without enabling Hermes runtime integration, live Gateway access, providers, credentials, network, or external effects.

**Architecture:** This is incremental hardening of an existing local/injected prototype. The Fleet repo retains coordination and persistence; Hermes owns session/runtime identity. The first integration surface remains one active `user_owned_session` observed read-only through the TUI backend. B15a.0's local host seam, B15a.1 lifecycle-only plugin, and B15a.2 injected contract remain evidence only; they are not runtime activation.

**Tech Stack:** Markdown normative contracts, local/injected test fixtures, existing PD Fleet/Hermes worktrees. No live process, provider, network, credential, installation, push, merge, release, or deploy.

---

## Baseline and non-negotiable boundary

- Fleet local execution is complete through `b0541db`; it does not promote Hermes readiness.
- B15a.0 local host seam: Hermes checkpoint `f66d3d4b06`, uninstalled/unactivated.
- B15a.1: default-off lifecycle-only `pd-fleet-hermes` package.
- B15a.2: Fleet-side injected `pd-fleet.session.snapshot` contract only.
- Current authoritative status stays `blocked_pending_plan_approval` and `NOT_READY_HERMES_SEAM` until every decision gate below is approved.
- `fleet_owned_task` is denied in v1.
- No user/client supplied `owner`, `principal`, `profile`, `workspace`, observer identity, capability, or authoritative session reference is trusted.

## Required decisions and owners

| ID | Required decision | Accountable approver | Cannot be inferred from |
|---|---|---|---|
| D1 | Public TUI RPC registration/dispatch API | Hermes runtime/TUI owner | local patch mechanics |
| D2 | Transport-to-session trusted identity chain | Hermes/TUI owner + security | injected host binding |
| D3 | Composite default-deny effective-capability policy | Hermes/TUI owner + security | plugin enablement |
| D4 | Closed wire vocabulary/schema/bounds/redaction | PD/Fleet + Hermes/TUI + security | local response projection |
| D5 | Snapshot/replay/cursor/outbox/restart semantics | PD/Fleet + Hermes/TUI + security | fake Gateway fixtures |
| D6 | Lifecycle authority and cleanup state machine | Hermes/TUI + security | registry unit tests |
| D7 | B15a.2 implementation authorization | Vitor + Hermes owner | B15a.0 worktree authorization |

## Task 1: Write the authoritative decision matrix

**Objective:** Convert candidates into explicit proposed decisions without marking them approved.

**Files:**
- Create: `.spec/pd-fleet-hermes-gateway-fleet-v1/B15A-DECISION-MATRIX.md`
- Reference: `B15A-EXECUTION-PLANS.md`, `B15-TUI-SEAM.md`, `G3-DELIVERY.md`, `G4-SECURITY.md`, `EXECUTION-AUTHORIZATION.md`

**Step 1: Write the matrix**

For D1–D6, include: decision statement, owner, alternatives rejected, evidence required, status `PROPOSED`, and the exact condition for `APPROVED`.

**Required proposed D1 contract:**
```text
Only an explicitly enabled plugin may register a versioned `fleet.*` handler.
The registry rejects collisions, isolates handler exceptions, rejects disabled/absent integration,
and preserves non-Fleet dispatch byte-for-byte.
```

**Required proposed D2/D3 rule:**
```text
Effective capability = plugin allow-list ∩ integration flag ∩ supported seam
∩ authenticated server-resolved caller ∩ active authoritative session
∩ explicit association ∩ capability allow-list ∩ current lifecycle state.
```

Any missing, stale, malformed, ambiguous, or hot-reloaded fact denies access.

**Verification:**
```bash
python3 scripts/pd_fleet/v2_doc_paths.py .
```
Expected: valid, 0 violations.

## Task 2: Freeze one B15a TUI wire vocabulary

**Objective:** Remove the ambiguity between TUI control-plane and bridge transport names.

**Files:**
- Create: `.spec/pd-fleet-hermes-gateway-fleet-v1/B15A-TUI-WIRE-CONTRACT.md`
- Modify: `B15-TUI-SEAM.md` only after D4 approval.

**Proposed v1 API:**
```text
fleet.session.activate
fleet.session.status
fleet.session.deactivate
fleet.session.replay
```

Bridge `connect/subscribe/disconnect` remains an internal transport mapping and is never an alias exposed to the TUI client.

**Schema requirements:**
- closed request/response/event/error schemas;
- schema version required;
- unknown field/enum rejected;
- opaque server-issued refs only;
- no free-form metadata maps;
- no prompt, history, tool/provider output, path, URL, token, credential, cookie, terminal frame, owner/profile/workspace identity.

**Proposed bounds pending security approval:**
```text
payload ≤ 4 KiB; envelope ≤ 8 KiB; replay batch ≤ 100;
activation TTL 5 min; idle TTL 90 s; heartbeat 30 s;
cursor TTL 15 min; reconnect grace 60 s.
```

**Verification:** Review the contract against `tests/fleet/test_tui_readonly_contract.py` and ensure every existing allowed field is represented or intentionally rejected.

## Task 3: Specify delivery, cursor, outbox and restart semantics

**Objective:** Make snapshot/replay/recovery implementable without silent loss or false synchronization.

**Files:**
- Create: `.spec/pd-fleet-hermes-gateway-fleet-v1/B15A-DELIVERY-RECOVERY-CONTRACT.md`
- Reference: `G3-DELIVERY.md`

**Required state machine:**
```text
pending_activation → observing → reconnecting → stale|orphaned|ended → detached
```

**Required ordering and durability rule:**
```text
validate envelope → redact → validate identity/association/provenance
→ persist event and outbox → advance ingestion cursor → deliver → record delivery ACK
```

**Required snapshot boundary:** Server returns atomically bound:
```text
snapshot + association_ref + subscriber_ref + stream_epoch + snapshot_sequence + boundary_ref
```
If unavailable: return `resync_required`; never claim synchronized state.

**Required crash matrix:** Before validation, after redaction, after event persist, after outbox persist, after cursor persist, before observer ack, reconnect, restart with continuity, restart without continuity, revoke/detach race, corrupted event/cursor/outbox.

**Verification:** Every crash row must name an expected durable state, replay response, and invariant forbidding silent cursor advance.

## Task 4: Define the B15a.2 local test matrix before implementation

**Objective:** Bind every contract decision to a RED test and acceptance artifact.

**Files:**
- Create: `.spec/pd-fleet-hermes-gateway-fleet-v1/B15A-TEST-MATRIX.md`

**Required test groups:**
1. absent/disabled/enabled/malformed plugin and feature flags;
2. non-Fleet golden compatibility;
3. namespace collision and handler exception isolation;
4. anonymous, foreign, forged, ambiguous and stale identity/binding;
5. no `fleet_owned_task` access;
6. closed schemas, unknown fields/enums and hostile nested/oversized/Unicode-control inputs;
7. recursive redaction over request, buffer, persistence, outbox, replay, log/audit and response;
8. duplicate attach/reconnect, association mismatch and lifecycle races;
9. snapshot-boundary, cursor expiry/tamper/stale, contiguous replay, no-new-events, replay-gap and resync;
10. all Task 3 crash points;
11. fake/injected canary: attach → event → replay → detach → cleanup.

Each row must name the future exact test path, fixture, expected error/status, and whether it requires only doubles or an approved real Hermes worktree.

## Task 5: Independent plan/security review

**Objective:** Turn proposed contracts into an honest approval packet.

**Files:**
- Create: `.spec/pd-fleet-hermes-gateway-fleet-v1/B15A-REVIEW-PACKET.md`
- Modify: `B15A-EXECUTION-PLANS.md` only with review verdict and unresolved D1–D7 entries.

**Review checklist:**
- no BLOCKER/HIGH in internal consistency;
- every D1–D6 maps to schema/state/test rows;
- all external/live scope stays out of scope;
- no candidate value is labeled approved without named approver;
- redaction happens before every storage/delivery boundary;
- no caller-controlled authority field is accepted;
- no promise of exactly-once external effects;
- clear rollback/default-off behavior.

**Expected verdict before owner decisions:** `PASS_WITH_EXTERNAL_DECISIONS` — not `APPROVED`.

## Task 6: Obtain decisions and create a scoped B15a.2 authorization

**Objective:** Only after D1–D6 receive named approvals, request narrowly scoped implementation authorization.

**Files:**
- Modify: `.spec/pd-fleet-hermes-gateway-fleet-v1/B15A-DECISION-MATRIX.md`
- Modify: `.spec/pd-fleet-hermes-gateway-fleet-v1/EXECUTION-AUTHORIZATION.md`
- Modify: `.spec/pd-fleet-hermes-gateway-fleet-v1/B15A-EXECUTION-PLANS.md`

**Authorization must name:**
- exact worktree, branch and base commit;
- allowed and forbidden files;
- local/default-off behavior;
- no canonical checkout mutation;
- no start/restart/reload, live calls, credentials, provider, network, push, merge, release or deploy;
- required TDD, reviews, gates and rollback.

**Gate:** Do not start B15a.2 code until D1–D7 are explicitly recorded as approved.

## Final verification

Before changing B15a status:
```bash
python3 scripts/pd_fleet/v2_doc_paths.py .
git diff --check
pytest -q tests/fleet/test_tui_readonly_contract.py
```

Expected: checks pass, but status remains `NOT_READY_HERMES_SEAM` until actual separately authorized B15a.2 implementation and real-path security evidence.

## Risks and out of scope

- This plan cannot manufacture Hermes owner/security approval.
- It does not activate, install, merge, or publish the local Hermes seam.
- It does not begin B15b messaging/API Gateway work.
- External effects remain at-least-once unless a later plan supplies idempotency/outbox/lease protocols appropriate to that effect.
