# B15a — Decision Matrix

**Status:** `PROPOSED_PENDING_NAMED_APPROVAL`  
**Readiness:** `NOT_READY_HERMES_SEAM`

This document closes ambiguity; it does not approve runtime integration.

| ID | Normative proposed decision | Required approver | Evidence to mark approved |
|---|---|---|---|
| D1 RPC seam | Only an explicitly enabled plugin may register versioned `fleet.*` handlers. Registration rejects collisions; disabled/absent handlers are denied; handler exceptions are bounded and isolated; non-Fleet dispatch is unchanged. | Hermes TUI/runtime owner | Public signature, non-Fleet golden tests, absent/disabled/collision/exception tests |
| D2 identity | Backend derives caller, TUI process, profile, workspace, authoritative active session and observer. Client authority fields are rejected. Missing/ambiguous binding denies. | Hermes TUI owner + security | Trusted transport/session binding design and negative tests |
| D3 capability | Effective capability is the intersection of plugin allow-list, integration flag, supported seam, authenticated caller, server-resolved active session, explicit association, capability allow-list and lifecycle state. | Hermes TUI owner + security | Decision table, malformed/hot-reload deny tests |
| D4 wire | TUI uses only `fleet.session.activate`, `status`, `deactivate`, `replay`; bridge transport names are internal. Schemas are closed/versioned/redacted/bounded. | PD/Fleet + Hermes TUI + security | Approved schema and recursive redaction/bounds tests |
| D5 delivery | Snapshot + association + subscriber + epoch + sequence + boundary are atomic; cursor is opaque, issuer-verifiable and bound. Persist event/outbox before cursor advance. | PD/Fleet + Hermes TUI + security | Replay/gap/crash/restart matrix and fake implementation evidence |
| D6 lifecycle | `pending_activation → observing → reconnecting → stale|orphaned|ended → detached`; revoke/session end/TUI exit/crash deny replay and clean association. | Hermes TUI owner + security | Transition table, race/recovery tests |
| D7 implementation | B15a.2 requires a separate scoped authorization naming worktree, base, files, tests, rollback and forbidden live effects. | Vitor + Hermes owner | Signed/recorded authorization after D1–D6 approval |

## Non-negotiable exclusions

No runtime activation, installation, restart/reload, provider, credentials, network, subprocess dispatch, session mutation, push, merge, release or deploy. `fleet_owned_task` remains denied.
