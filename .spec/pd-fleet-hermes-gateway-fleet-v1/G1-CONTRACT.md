# G1 — Hermes Gateway → PD Fleet Bridge Contract

**Status:** `local_verified_live_open`
**Scope:** local/fake/injected implementation and verification; live Hermes seam excluded
**Version:** `pd-fleet-gateway-bridge:v1`
**External effects:** disabled
**Implementation authorization:** local/fake/injected only; no live runtime/production

## 1. Purpose and boundary

This document defines the proposed, Hermes-owned bridge contract for a PD Fleet client to observe a user-owned Hermes session through the Hermes Gateway.

It is a design contract, not evidence that the commands or event stream already exist in Hermes. The current dashboard channel (`/api/events?channel=...`) is explicitly **not** this contract: it is scoped to an in-memory PTY/chat channel and has no global discovery, cursor, replay, or durable event semantics.

The bridge sits at this boundary:

```text
Hermes Runtime / Session
  → Hermes Gateway
  → Fleet Gateway Bridge
  → PD Fleet
  → PD Core
```

Authority remains separated:

- Hermes Runtime/Gateway owns concrete sessions, runtime state, providers, models, tools, capabilities, and native event delivery.
- Fleet Gateway Bridge translates the supported Gateway surface without becoming a second runtime authority.
- PD Fleet owns association, coordination, lifecycle, leases, checkpoints, reconciliation, and reports.
- PD Core owns goal, SPEC, PLAN, DAG, acceptance, gates, human decisions, and merge/release decisions.

## 2. Activation and association are separate from observation

The initial flow is:

```text
user starts Hermes
  → user submits an explicit PD goal or Fleet coordination request
  → Hermes emits a bounded activation/association signal
  → Fleet client registers through the supported Gateway extension
  → Fleet observes the associated user-owned session
```

Activation MUST NOT be inferred from arbitrary prompt text, generic content, or the existence of a Hermes session. The activation signal does not grant control.

The proposed activation artifact is metadata-only:

```json
{
  "activation_ref": "gateway-owned-opaque-ref",
  "association_ref": "gateway-owned-opaque-ref",
  "session_ref": "gateway-owned-opaque-ref",
  "owner_ref": "bounded-opaque-ref",
  "profile_ref": "bounded-opaque-ref",
  "workspace_ref": "bounded-opaque-ref",
  "ownership_mode": "user_owned_session",
  "purpose": "pd_observation",
  "issued_at": "gateway-timestamp",
  "expires_at": "gateway-timestamp",
  "nonce_ref": "gateway-owned-opaque-ref",
  "capabilities": ["observe_session_metadata"]
}
```

The artifact MUST be issued by an authenticated Hermes-owned boundary, scoped to the owner/profile/workspace that requested the association, bounded by an expiry, and single-use or idempotent by `activation_ref`/`nonce_ref`. The exact transport authentication and replay-protection mechanism remains a G4 design question; a caller-supplied activation object is never proof of authorization.

The initial association mode is:

```text
user_owned_session = read-only, default-deny
```

`fleet_owned_task` is out of this contract and requires a later, separately authorized ownership/capability/lease protocol.

## 3. Proposed command surface

These names describe the versioned bridge contract and remain **proposed** until G0–G5 review identifies the supported Hermes seam:

- `fleet.connect`
- `fleet.subscribe`
- `fleet.disconnect`

The client MUST provide a bounded client identity and requested event version. The Gateway MUST authenticate the transport and apply a Fleet-specific authorization policy before returning session data. A caller-supplied field is not itself proof of identity or ownership.

`fleet.subscribe` is scoped to an explicit association/session reference. A wildcard subscription over all Hermes sessions is not part of v1.

### Vocabulary boundary with B15a TUI

G1 bridge commands and B15a TUI control operations are separate layers:

| Layer | Vocabulary | Meaning |
|---|---|---|
| TUI control plane | `activate`, `status`, `deactivate` | local operations on the one authoritative active TUI session |
| Fleet bridge transport | `fleet.connect`, `fleet.subscribe`, `fleet.disconnect` | proposed observer connection/subscription lifecycle at the bridge boundary |

The table is a mapping proposal, not evidence that either surface exists in Hermes. Before implementation, the Hermes owner must select one authoritative wire vocabulary and document the translation, authentication context, collision policy, error/version behavior, and default-off behavior. An implementer must not silently alias one layer to the other.

The authorization granted by this contract is observation-only:

| Capability | Initial v1 |
|---|---|
| register an authenticated Fleet observer | allowed |
| associate an explicitly activated user-owned session | allowed, scoped and bounded |
| receive redacted lifecycle/operational metadata | allowed |
| receive prompts, history, tool arguments/results, provider responses, credentials, or terminal frames | denied |
| dispatch, prompt injection, cancellation, tool execution, provider activation, or session mutation | denied |
| claim `fleet_owned_task` ownership | denied; future authorization |

Gateway authentication/authorization for this observer surface MUST NOT be interpreted as runtime authorization. It only permits the bounded observation operations listed above.

## 4. Versioned event envelope

Every accepted event uses this logical envelope:

```json
{
  "schema_version": "pd-fleet-gateway-bridge:v1",
  "event_id": "gateway-owned-opaque-id",
  "event_type": "session.registered",
  "occurred_at": "gateway-timestamp",
  "source": {
    "system": "hermes-gateway",
    "instance_ref": "bounded-opaque-ref"
  },
  "event_origin": "gateway_native",
  "session": {
    "session_ref": "gateway-owned-opaque-ref",
    "association_ref": "bounded-opaque-ref",
    "ownership_mode": "user_owned_session"
  },
  "stream_epoch": "bounded-opaque-ref",
  "sequence": 42,
  "payload": {},
  "provenance": {
    "transport": "gateway-event-stream",
    "correlation_id": "bounded-opaque-ref"
  }
}
```

Envelope requirements:

- `schema_version`, `event_id`, `event_type`, `occurred_at`, `source`, `session`, `stream_epoch`, and `sequence` are required.
- IDs and references are opaque, bounded, and must not contain prompts, credentials, filesystem paths, provider responses, or terminal content.
- `payload` is event-specific metadata only and has a bounded size defined by the implementation authorization packet.
- `provenance` records origin/correlation metadata; it is not an authorization claim.
- `event_origin` is `gateway_native` for Hermes-emitted events and `fleet_reconciled` only for a Fleet-derived reconciliation record. Fleet MUST NOT republish a derived record as a native Gateway event.
- The Gateway is authoritative for event delivery and native session identity; Fleet is authoritative for its translated association record.
- Redaction happens before persistence, translation, or external delivery.

## 5. Initial event allowlist

The v1 initial stream contains lifecycle and operational metadata only:

- `session.registered`
- `session.status_changed`
- `session.heartbeat`
- `session.metadata_changed`
- `session.detached`
- `session.ended`

The initial payload MUST NOT contain prompts, conversation history, tool arguments/results, provider responses, credentials, secrets, terminal frames, or arbitrary message content.

The initial event payloads are closed schemas; unknown keys are rejected. The proposed allowlist is:

| Event | Allowed payload fields | Constraints |
|---|---|---|
| `session.registered` | `runtime_surface`, `metadata_version` | `runtime_surface` is an enum; `metadata_version` is a bounded integer |
| `session.status_changed` | `status`, `reason_code`, `metadata_version` | status/reason are bounded enums; no free-form detail |
| `session.heartbeat` | `heartbeat_sequence`, `observed_at`, `ttl_ms` | sequence/integer bounds and bounded TTL; no content |
| `session.metadata_changed` | `metadata_version`, `changed_fields` | closed enum list only; no arbitrary metadata map or values |
| `session.detached` | `reason_code`, `metadata_version` | bounded enum; no free-form detail |
| `session.ended` | `terminal_state`, `reason_code`, `metadata_version` | bounded enums; no transcript or result content |

All enum values, maximum list cardinality, integer ranges, payload sizes, and redaction rules remain to be frozen by G4. Until then, unknown fields and values fail closed.

`tool.*`, `message.*`, approval events, provider events, and content-bearing events are **future extensions**, not part of the initial v1 stream. Any future extension requires a new schema/allowlist review and separate capability decision.

## 6. Unknown events and malformed data

The bridge uses fail-closed handling:

- malformed envelopes are rejected and audited as `invalid_event`; they are not persisted or forwarded;
- unknown event types are not silently treated as successful data; they produce a bounded `unsupported_event` diagnostic and do not mutate Fleet state;
- unsupported schema versions require an explicit compatibility decision and are rejected by default;
- oversized fields/payloads are rejected before persistence;
- missing association, foreign ownership, stale authorization, and invalid provenance are explicit errors;
- no error response may include raw prompt, provider, credential, or terminal data.

Unknown-event handling MUST preserve the distinction between “no event available” and “event could not be safely understood.”

## 7. Canonical error taxonomy

These codes are normative across G1, G2, G3, and G4:

| Code | Meaning | Retry/reveal policy |
|---|---|---|
| `invalid_request` | request/cursor shape is malformed but does not expose runtime data | reject without state mutation |
| `unauthenticated` | transport/client identity is absent or invalid | retry only after authentication; do not reveal session existence |
| `observer_not_authorized` | authenticated observer lacks the bounded capability | no automatic retry; do not reveal unscoped session data |
| `activation_invalid` | artifact is malformed, unknown, revoked, or not issuer-verifiable | no retry without a new artifact |
| `activation_expired` | artifact TTL has elapsed | obtain a new explicit activation |
| `activation_replayed` | single-use nonce/activation was already consumed | no retry with the same artifact |
| `activation_binding_mismatch` | requested binding differs from the issuer-bound artifact | no retry without a matching artifact |
| `foreign_owner` | owner/profile/workspace does not match the authorized binding | no retry under the foreign binding |
| `association_required` | no valid explicit association exists | do not infer or auto-create one |
| `association_stale` | association exists but is expired/orphaned/detached | reconcile or create a new explicit association |
| `invalid_provenance` | origin/correlation cannot be trusted | reject and quarantine; no forwarding |
| `unsupported_schema` | event/request schema is not supported | no retry without negotiated compatibility |
| `unsupported_event` | event type is not in the allowlist | no state mutation; bounded diagnostic |
| `invalid_event` | envelope or payload is malformed | no persistence or forwarding |
| `payload_too_large` | field/list/payload exceeds the active bound | no retry without bounded payload |
| `capability_denied` | requested operation exceeds the mode capability | no retry unless separately authorized |
| `cursor_expired` | cursor TTL elapsed | request a new snapshot/resubscribe |
| `cursor_stale` | cursor epoch/retention is no longer valid | resync snapshot or reassociate |
| `replay_gap` | requested sequence is no longer continuously retained | explicit resync; no success claim |
| `resync_required` | atomic snapshot/boundary could not be proven | snapshot/resubscribe |
| `no_new_events` | valid cursor has no subsequent event | remain synchronized; do not advance falsely |

Error responses MUST not disclose whether an unscoped session exists. `association_stale` is used for a previously authorized reference; `association_required` is used when no authorized association can be acknowledged.

## 8.1 Pre-implementation closure requirements

The following remain blockers for any live seam implementation:

- public RPC registration/dispatch contract and owner approval;
- trusted identity binding for transport, process, profile, workspace, session, and observer, including ambiguous/missing identity rejection;
- composite default-deny evaluation with malformed/missing configuration;
- normative closed schemas and bounds for every request, response, event, diagnostic, and intermediate buffer;
- redaction-before-buffer/persistence/replay/logging evidence;
- snapshot/stream atomicity, cursor issuer/binding, epoch, retention, tombstones, outbox/ack ordering, heartbeat/TTL/grace, and restart recovery.

Until these are closed, G1 remains a design contract only and cannot authorize B15a implementation or change `NOT_READY_HERMES_SEAM`.

## 8. Registration ordering and G3 dependency

`session.registered` is a native Gateway lifecycle event, not proof that a Fleet observer is authorized. The bridge MUST establish/validate the explicit activation and association before exposing that event to Fleet.

The initial snapshot/replay ordering, whether `session.registered` is synthesized for an already-running session, and the cursor needed to avoid loss or duplication are G3 decisions. Until G3 closes, no implementation may assume that a live subscription alone recovers registration history.

## 9. Correlation and idempotency

- `event_id` is the Gateway event identity and is used for deduplication by the Fleet bridge.
- `correlation_id` links a bounded activation/association operation to resulting lifecycle events.
- Re-delivery of the same `event_id` MUST be idempotent at the Fleet association boundary.
- Ordering, cursor, replay, reconnect, gap, snapshot-before-stream, and stale-session semantics are specified in G3; this G1 envelope does not invent a durable ordering guarantee.
- Activation/association must not be reconstructed from arbitrary event content.

## 8. Explicit non-goals

This contract does not authorize:

- dispatch, prompt injection, cancellation, or control of a user-owned session;
- provider/model activation;
- credential access;
- filesystem mutation or subprocess control;
- direct Hermes `state.db` reads/writes;
- ACP/private Hermes internals as a Fleet protocol;
- network exposure, production deployment, HA, or release;
- a dashboard-dependent implementation.

## 10. G1 review questions

G1 is not complete until review resolves or explicitly carries forward:

1. Which existing Hermes-owned transport/extension will implement `fleet.connect` and `fleet.subscribe`?
2. What exact transport authentication context is available to bind a Fleet client to an authorized owner/profile/workspace?
3. Which session reference is stable across Gateway reconnect and runtime restart?
4. Which metadata fields are safe and necessary for each allowlisted event?
5. What bounded event size, retention, and redaction policy will feed G3/G4?
6. How does the bridge distinguish a user-owned session from a separately authorized Fleet-owned task?

A completed G1 review does not authorize G6 implementation. That requires a new explicit implementation authorization naming files, process, transport, capabilities, rollback, and verification evidence.
