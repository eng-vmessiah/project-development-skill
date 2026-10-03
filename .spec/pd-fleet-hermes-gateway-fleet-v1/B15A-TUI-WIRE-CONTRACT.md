# B15a TUI Wire Contract v1

**Status:** `PROPOSED_PENDING_D4_APPROVAL`  
**Scope:** one server-resolved `user_owned_session`, read-only/default-deny.

## Public vocabulary

Only these client operations are proposed:

```text
fleet.session.activate
fleet.session.status
fleet.session.deactivate
fleet.session.replay
```

`connect`, `subscribe`, and `disconnect` are internal bridge transport terms and MUST NOT be public aliases.

## Authority boundary

The request may contain only schema version and operation-specific opaque, bounded protocol values. It MUST NOT establish or override caller, owner, principal, profile, workspace, observer, capability, association, or authoritative session. The backend resolves those facts; absent or ambiguous facts deny.

## Closed operation and snapshot schemas

Every request and response is an object with `schema_version` and no unknown fields. `activate` request is `{schema_version}` only; success returns bounded opaque `association_ref`, `subscriber_ref`, `stream_epoch`, `cursor` and `snapshot`. `status` is `{schema_version}` and returns only the same bounded snapshot. `deactivate` is `{schema_version}` and returns `{schema_version,status:"detached"}`. `replay` is `{schema_version,cursor}` and returns `{events:[Event],next_cursor}` or one canonical bounded error. No request accepts identity, session, capability or association authority.

`Snapshot` is closed: `{association_ref,stream_epoch,snapshot_sequence,boundary_ref,state,metadata_version}`. It contains no arbitrary metadata and is redacted/validated at every boundary exactly as events.

## Envelope and event schema

All envelopes require `schema_version: "pd-fleet-tui:v1"`. Unknown fields/enums fail closed.

```json
{
  "schema_version": "pd-fleet-tui:v1",
  "event_id": "opaque-ref",
  "event_type": "session.status_changed",
  "association_ref": "opaque-ref",
  "stream_epoch": "opaque-ref",
  "sequence": 42,
  "payload": {"status": "closed-enum", "reason_code": "closed-enum", "metadata_version": 1}
}
```

Allowed event types: `session.registered`, `session.status_changed`, `session.heartbeat`, `session.metadata_changed`, `session.detached`, `session.ended`.

`event_id` and `sequence` are one-to-one inside `(association_ref, stream_epoch)`. For that scope, `sequence` is a non-negative integer, unique, strictly increasing and contiguous while retained. Snapshot contains state through `snapshot_sequence`; `boundary_ref` binds that cut; replay returns only events with `sequence > snapshot_sequence` or cursor last sequence. A repeated sequence with another event, out-of-order event, or retained discontinuity is `invalid_provenance` or `replay_gap`; it never silently succeeds. `occurred_at` is informational, never ordering authority.

## Redaction and bounds

Redact/reject before buffer, persistence, outbox, replay, logs, metrics or response. Never permit prompts, history, messages, tool inputs/outputs, provider material, tokens, credentials, cookies, URLs, filesystem paths, terminal frames, or identity values.

Proposed approval bounds: payload ≤4 KiB; serialized envelope ≤8 KiB; replay ≤100 events; no arbitrary maps; finite depth/cardinality/string/opaque-ref limits; reject control/bidi Unicode, binary, NaN/infinity and unknown structure.

## Canonical errors

`invalid_request`, `unsupported_schema`, `observer_not_authorized`, `association_stale`, `cursor_expired`, `cursor_stale`, `replay_gap`, `resync_required`, `invalid_event`, `invalid_provenance`, `no_new_events`. Diagnostics contain only stable code and opaque references.
