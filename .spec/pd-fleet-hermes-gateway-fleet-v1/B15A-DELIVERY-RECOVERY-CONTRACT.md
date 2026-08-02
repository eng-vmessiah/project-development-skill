# B15a Delivery and Recovery Contract

**Status:** `PROPOSED_PENDING_D5_D6_APPROVAL`

## Synchronization and ordering

Server issues atomically: `snapshot`, `association_ref`, `subscriber_ref`, `stream_epoch`, `snapshot_sequence`, `boundary_ref`. If it cannot, return `resync_required`; never claim synchronization.

Order is scoped to `(association_ref, stream_epoch, sequence)`. Cursor is opaque, issuer-verifiable, bound to association/subscriber/epoch and never created, edited or transferred by Fleet.

## Durable processing order

```text
validate envelope → redact → validate identity/association/provenance
→ persist event + outbox → advance ingestion cursor → deliver → record ACK
```

Observer ACK is separate and may be retried from outbox. A gap, invalid event, stale epoch or provenance conflict blocks cursor advancement.

## Replay and restart

- contiguous retained history: ordered events after cursor;
- valid end cursor: `no_new_events`;
- retained start after cursor: `replay_gap` plus resync instruction;
- expired/tampered/foreign cursor: bounded denial;
- restart with proven continuity: same epoch/cursor;
- otherwise: new epoch + resync or stale/orphaned; never silent reset.

## Lifecycle

```text
pending_activation → observing → reconnecting → stale|orphaned|ended → detached
```

TTL/heartbeat are liveness, not authorization. Revoke, session end, TUI exit, crash or detach deny replay until explicit valid reassociation.

## Retention, invalidation and reassociation

Authorization and lifecycle are revalidated before reading any snapshot, history or outbox. `detach`, revoke and TTL expiry irreversibly invalidate their association, subscriber, epoch and every cursor immediately; records are tombstoned before bounded purge and pending outbox is cancelled rather than delivered. `ended` is terminal and is never reassociable. Crash may retain only opaque tombstones and idempotent durable records required for recovery; it never reuses a prior authority binding.

Only `fleet.session.activate`, after fresh D2/D3 server-side authentication and resolution, may create an association. It always emits new association/subscriber refs, epoch, atomic snapshot/boundary and cursor. Reuse of any pre-revocation ref/cursor is `invalid_provenance` or `association_stale`.

## Required crash invariants

| Failure point | Required result |
|---|---|
| before validation/redaction | no persist/outbox/cursor/ack |
| after redaction before persist | cursor unchanged; safe reprocess |
| after event before outbox | reconstruct/retry idempotently |
| after outbox before cursor | dedupe then advance only after durability check |
| after cursor before ACK | outbox retries; no loss |
| snapshot/boundary unavailable | `resync_required` |
| continuity unknown after restart | no replay success; new epoch/resync/stale |
| revoke racing cleanup | authoritative validation denies new replay |
