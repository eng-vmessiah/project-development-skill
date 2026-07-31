# G3 — Cursor, Replay, Reconnect, and Stale Semantics

**Status:** `local_verified_live_open`
**Scope:** local/fake/injected implementation and verification; live Hermes seam excluded
**Implementation authorization:** local/fake/injected only; no live runtime/production
**External effects:** disabled

## 1. Purpose and boundary

This packet defines how the proposed Hermes Gateway → Fleet Bridge delivers the bounded v1 lifecycle stream after an explicit `user_owned_session` association.

It does not establish that Hermes currently provides these semantics. It is a reconciliation contract for a future supported seam. The existing dashboard channel remains out of scope because it has no global discovery, durable cursor, replay, or gap contract.

## 2. Delivery model

The v1 observer uses a snapshot-before-stream sequence:

```text
1. authenticate observer
2. validate activation/association
3. obtain bounded association snapshot
4. establish a stream boundary
5. replay events after the requested cursor/boundary
6. deliver live events after replay
7. heartbeat and reconcile liveness
```

The bridge MUST NOT report the association as synchronized until the snapshot and replay boundary are explicit. A live subscription without a known boundary is not proof that `session.registered` or earlier lifecycle events were observed.

## 3. Event ordering

Ordering is scoped to one association, not global across Hermes:

```text
association_ref + stream_epoch + sequence
```

- `sequence` is a monotonically increasing integer within an association/epoch.
- `event_id` remains the deduplication identity.
- Events from different associations have no ordering relationship.
- `occurred_at` is informational and MUST NOT replace sequence ordering.
- A reconnect may produce duplicate delivery; it MUST NOT produce silent reordering or claim a gap is complete.
- A new `stream_epoch` is issued after a Gateway/Fleet restart when the previous sequence continuity cannot be proven.

The exact numeric bounds and persistence guarantees remain implementation-authorization decisions.

## 4. Cursor contract

The cursor is opaque to Fleet application code. Its logical claims are:

```json
{
  "cursor_version": "pd-fleet-gateway-bridge:v1",
  "association_ref": "gateway-owned-opaque-ref",
  "subscriber_ref": "bounded-observer-ref",
  "stream_epoch": "bounded-opaque-ref",
  "last_sequence": 42,
  "issued_at": "gateway-timestamp",
  "expires_at": "gateway-timestamp"
}
```

The serialized cursor MUST be authenticated or otherwise issuer-verifiable by the supported Gateway seam. Fleet MUST NOT construct, edit, or transfer a cursor between associations/subscribers.

Cursor validation MUST reject:

- malformed or unsupported cursor versions → `invalid_request` or `unsupported_schema`;
- foreign association/subscriber binding → `activation_binding_mismatch` or `observer_not_authorized`;
- expired cursor → `cursor_expired`;
- unknown/restarted epoch → `cursor_stale`;
- tampered or unverifiable cursor → `invalid_provenance`.

The final transport representation and signing/key-rotation mechanism remain G4 decisions.

## 5. Replay and gap semantics

A replay request means: deliver all accepted events with sequence greater than the cursor's `last_sequence` within the same association/epoch, subject to the bounded limit.

| Condition | Required result |
|---|---|
| valid cursor and contiguous retained history | replay events in sequence order |
| no events after cursor | explicit `no_new_events`, not success-with-missing-data |
| duplicate event already acknowledged | suppress state mutation; preserve idempotent delivery |
| retained history starts after requested sequence | `replay_gap` with resync instruction |
| unknown epoch | `cursor_stale` with snapshot/resubscribe required |
| event cannot be safely decoded | `invalid_event`; do not advance past it silently |
| requested limit exceeds bound | `payload_too_large` or bounded-limit error |
| association expired/detached | `association_stale`; no further replay |

A gap is never converted into an empty successful replay. The bridge MUST return a bounded diagnostic containing:

- association reference;
- requested cursor/boundary reference;
- observed retained start sequence, if safe to disclose;
- required action: `resync_snapshot` or `reassociate`;
- no raw runtime content.

## 6. Snapshot-before-stream

The bridge MUST obtain `snapshot_sequence`, `stream_epoch`, and a Gateway-issued `stream_boundary_ref` atomically from the supported Gateway seam. The boundary token represents the first sequence eligible for replay/live delivery and MUST be bound to the association/subscriber. If the Gateway cannot issue this tuple atomically, it MUST return `resync_required`; separate unbound snapshot and subscribe calls MUST NOT claim synchronization.

The initial snapshot contains only the bounded association/session metadata permitted by G1/G4. It MUST include a synchronization marker:

```json
{
  "snapshot_version": "pd-fleet-gateway-bridge:v1",
  "association_ref": "opaque-ref",
  "stream_epoch": "opaque-ref",
  "stream_boundary_ref": "gateway-issued-opaque-ref",
  "snapshot_sequence": 42,
  "state": "observing",
  "expires_at": "gateway-timestamp"
}
```

The stream boundary is the sequence immediately after `snapshot_sequence`. Events at or below the snapshot marker are not replayed again unless an explicit resync requests them. Events after it are delivered in sequence order.

If the Gateway cannot provide an atomic snapshot/boundary, it MUST return `resync_required` rather than claim synchronized state.

## 7. Reconnect and recovery

Reconnect is a new authenticated subscription using the last acknowledged cursor. The bridge MUST:

1. re-authenticate the observer;
2. revalidate association binding and TTL;
3. validate cursor version, subscriber, association, and epoch;
4. replay from the last acknowledged sequence;
5. deduplicate by `event_id` and sequence;
6. expose a gap/resync result instead of silently advancing;
7. emit a bounded reconciliation outcome.

The bridge MUST NOT advance the durable ingestion cursor before the event has passed envelope validation, redaction, association validation, and durable event/outbox persistence. Observer delivery acknowledgement is a separate outcome and may be retried from the outbox.

Within one `(association_ref, stream_epoch)`, the identity relation is strict: one `sequence` maps to one `event_id`, and one `event_id` maps to one `sequence`. A duplicate pair is idempotent; either conflict is `invalid_provenance` and MUST stop cursor advancement until resync.

## 8. Heartbeat, TTL, and stale states

Heartbeat is liveness metadata, not evidence of runtime control or user approval.

Proposed association states:

```text
pending_activation
observing
reconnecting
stale
orphaned
ended
detached
```

- `observing`: latest heartbeat is within the agreed TTL.
- `reconnecting`: observer transport is temporarily absent but the association has not expired.
- `stale`: heartbeat/activation TTL has elapsed; replay and observation are denied with `association_stale` until explicit reassociation.
- `orphaned`: Fleet retains bounded lineage but the Hermes session cannot be resolved; no runtime action is attempted.
- `ended`: Hermes reported terminal session state; observation closes.
- `detached`: observer relationship was explicitly removed; the Hermes session remains untouched.

The exact heartbeat interval, TTL, grace period, and clock-skew allowance are G4-owned bounds and MUST be explicit before implementation.

## 9. Restart recovery

A restart MUST be fail-closed when sequence continuity, cursor integrity, or association provenance cannot be proven.

Allowed recovery outcomes:

- resume from a valid cursor in the same epoch;
- issue a new epoch and require snapshot/resubscribe;
- mark the association stale/orphaned and require explicit reassociation.

A restart MUST NOT fabricate missing events, silently reset the cursor to zero, or convert an unverified gap into success.

## 10. Canonical G3 errors

The following additions extend the canonical G1 taxonomy:

| Code | Meaning | Required action |
|---|---|---|
| `cursor_expired` | cursor TTL elapsed | request a new snapshot/resubscribe |
| `cursor_stale` | cursor epoch/retention is no longer valid | resync snapshot or reassociate |
| `replay_gap` | requested sequence is no longer continuously retained | explicit resync; no success claim |
| `resync_required` | atomic boundary/snapshot could not be proven | snapshot/resubscribe |
| `no_new_events` | valid cursor has no subsequent event | remain synchronized; do not advance falsely |

These codes are bounded and must not reveal unscoped session existence or raw runtime content.

## 11. Open decisions for G3/G4 closure

- exact cursor serialization and issuer verification;
- sequence persistence and retention source;
- atomic snapshot/boundary mechanism;
- cursor acknowledgement semantics and durable write ordering;
- heartbeat interval, TTL, grace, and clock-skew limits;
- restart epoch issuance and recovery evidence;
- transport retry/backoff bounds;
- redacted reconciliation/audit retention.
