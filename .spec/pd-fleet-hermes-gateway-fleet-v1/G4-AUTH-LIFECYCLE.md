# G4 — Opaque Activation Ticket Lifecycle

**Status:** `local_verified_live_auth_open`
**Scope:** local/fake/injected lifecycle verified; live Hermes Gateway lifecycle remains unimplemented
**Implementation authorization:** local repository only, as bounded by `EXECUTION-AUTHORIZATION.md`
**External effects:** disabled

This packet defines and locally tests the lifecycle of the approved opaque Gateway-issued activation-ticket design. It does not define or implement a current Hermes Gateway API, and local fixture success is not live issuer readiness.

## 1. Ticket record

The ticket value is an opaque, bounded reference with no raw claims. The Gateway-side record is the authority:

```text
activation_ref
observer_ref
owner_ref
profile_ref
workspace_ref
session_ref
association_ref
ownership_mode = user_owned_session
purpose = pd_observation
issued_at
expires_at
nonce_ref
status
consumed_at?
revoked_at?
provenance_ref
```

The record MUST be bound to the authenticated Gateway observer identity. Fleet receives only the opaque ticket and bounded outcome data.

## 2. Ticket state machine

The ticket lifecycle is independent from the association lifecycle:

```text
issued
  ├─ valid atomic consume ───────→ consumed
  ├─ present after expiry ────────→ expired
  ├─ present after revoke ────────→ revoked
  ├─ present with prior consume ──→ replay_rejected
  ├─ wrong observer/binding ──────→ binding_rejected
  └─ malformed/unknown ───────────→ invalid
```

Persisted ticket states are:

```text
issued
consumed
expired
revoked
```

`replay_rejected`, `binding_rejected`, and `invalid` are presentation outcomes, not new persisted ticket states. A ticket is consumed at most once. A valid ticket consumed for a valid association MUST NOT be reused to create another association.

## 3. Association state machine

The association lifecycle is separate:

```text
pending_activation
  ├─ atomic consume + association commit ─→ observing
  ├─ session/owner binding invalid ───────→ rejected
  └─ activation expires/revokes ──────────→ rejected

observing ── missed heartbeat ─→ reconnecting
reconnecting ── grace exceeded ─→ stale
observing ── session ends ──────→ ended
observing/reconnecting ── detach → detached
stale + explicit reassociation ─→ pending_activation
```

Association states are not ticket states. `stale`, `ended`, and `detached` do not mutate the Hermes session and do not automatically mint or renew a ticket.

## 4. Atomic consume and association commit

The Gateway-owned consume operation MUST behave as one logical transaction:

```text
authenticate observer
→ resolve opaque ticket
→ validate issuer/version/purpose/expiry
→ validate observer + owner/profile/workspace/session/association binding
→ check status = issued and nonce unused
→ atomically mark consumed
→ create or return the idempotent association result
```

The consume transaction MUST include ticket status, nonce consumption, and association creation in one authoritative transaction boundary. If the Gateway cannot provide that boundary, the operation is unsupported and MUST return `activation_invalid`; it MUST NOT consume first and repair later.

Concurrency requirements:

- the Gateway serializes or atomically compares presentations by `activation_ref`;
- two simultaneous presents produce at most one new association;
- the committed idempotency record stores the bounded association result;
- a retry with the same operation key returns that stored bounded result;
- a different operation key receives the uniform external rejection and no association details;
- consume and association creation cannot leave a half-created ownership record.

## 5. Idempotency

The bounded operation key is:

```text
(activation_ref, observer_ref, association_ref, purpose)
```

A retry of the same authenticated operation may return the same bounded association result if the original consume committed. A retry with a different observer, owner/profile/workspace, session, association, or purpose MUST fail closed.

Idempotency records MUST contain no raw prompt, history, tool, provider, credential, or terminal content.

## 6. External failure uniformity

For a ticket presentation/activation request, the external response for unknown, malformed, expired, revoked, replayed, binding-mismatch, foreign-owner, stale, ended, or wrong-purpose inputs MUST be the same bounded `activation_invalid` outcome. It MUST use equivalent response shape and apply an equivalent timing budget; it MUST NOT reveal session, owner, association, or ticket existence.

Internal audit may retain a more specific reason (`activation_expired`, `activation_replayed`, `activation_binding_mismatch`, `foreign_owner`, `association_stale`, `capability_denied`) with opaque references and no raw runtime content.

## 7. Expiry and revocation

Expiry and revocation are Gateway-authoritative. External presentation responses remain uniformly `activation_invalid`; the following reasons are internal audit outcomes only:

- expired ticket → audit `activation_expired`;
- revoked ticket → audit `activation_invalid`;
- consumed ticket → audit `activation_replayed` unless it is the exact bounded idempotent retry;
- session ended before presentation → audit `association_stale`;
- owner/profile/workspace changed → audit `activation_binding_mismatch` or `foreign_owner`;
- purpose other than `pd_observation` → audit `capability_denied`.

Revocation MUST prevent future presentation and prevent creation of a new association. Existing read-only association cleanup/reconciliation is a separate bounded operation and MUST NOT mutate the Hermes session.

## 8. Crash and recovery cases

| Crash point | Required recovery |
|---|---|
| before consume commit | ticket remains `issued`; retry may present it |
| during consume/association transaction | transaction is atomic: either both ticket consumption and association commit persist, or neither persists; no repair alternative |
| after association commit, before response | idempotent retry returns the same bounded result |
| after ticket expiry, before cleanup | external result remains uniform `activation_invalid`; cleanup is asynchronous |
| after revocation request, before cleanup | validation consults authoritative revocation state; no new association |
| after Gateway restart | issued/consumed/revoked state is recovered from authoritative durable state, or all uncertain records become invalid/stale; never accept uncertain replay |

## 9. Required negative fixtures

G5 local fixtures cover these cases without connecting to live Hermes. The fixture result verifies the local policy only; it does not verify a Hermes issuer or Gateway API.

- valid first presentation;
- duplicate presentation;
- concurrent duplicate presentation;
- wrong observer;
- wrong owner/profile/workspace;
- wrong session/association;
- wrong purpose;
- expired ticket;
- revoked ticket;
- malformed/unknown ticket;
- crash before consume commit;
- crash after consume before response;
- restart with uncertain consumption;
- no session-existence disclosure on failure.

## 10. Open live Hermes decisions

- concrete Hermes transport authentication;
- Gateway ticket issuance/consume API;
- authoritative storage and atomic transaction boundary;
- final TTL, clock-skew, cleanup, and replay-tombstone bounds;
- revocation source and propagation latency;
- exact idempotent retry response semantics;
- security review and live negative-fixture evidence.

The planned order for resolving these decisions is now explicit:

1. **B15a — TUI backend first:** use the local `tui_gateway` JSON-RPC/stdio caller, derive the principal and active session server-side, and keep the initial association session-scoped.
2. **B15b — messaging Gateway second:** separately resolve API/Discord/Telegram caller authentication, multi-session/global subscription, and operational rollback.

The TUI plan is recorded in `B15-TUI-SEAM.md`. Selecting it as the first candidate does not change the current status: the TUI observer is not wired, the feature remains default-off, and live readiness remains `NOT_READY_HERMES_SEAM`.

These local lifecycle rules are verified only against injected doubles. The fixture result verifies local policy only; it does not verify a Hermes issuer or Gateway API. G4 is locally verified with live auth open; G5 local verification and G6 local implementation are authorized by `EXECUTION-AUTHORIZATION.md`. The live Hermes Gateway remains `NOT_READY_HERMES_SEAM` until the open decisions are implemented, reviewed, separately authorized, and validated.
