# Concurrent Stateful Workflow Checklist

Use this reference when planning approval, queue, executor, scheduler, or other persisted state machines.

## Pre-implementation

- Identify the single transition table and make API, unit code, and persistence call it.
- Separate persistence-only activation from real dispatch.
- Define public versus internal fields; redact recursively, including nested snapshots.
- Define whether every `idempotency_key` is deduplicated and replayable. If not, remove or rename it.

## Transaction boundary

The transaction must cover the complete invariant:

```text
lock
→ reread current plan and approval
→ validate owner, revision, hash, and decision
→ build immutable snapshot
→ check idempotency fingerprint
→ apply all state transitions
→ append audit events
→ commit
```

Do not validate from an API-fetched object and then pass that stale object into a locking function. That is a TOCTOU race.

For multi-event dry-runs, use one transaction. A failed `queued → preparing → running` command must not leave `preparing` committed.

## Tests required

- approval changed while activation waits for the lock;
- plan revision/hash changed while activation waits;
- two activations with the same idempotency key;
- same idempotency key with a different fingerprint;
- concurrent start and cancel/pause;
- invalid transitions from queued, terminal, and unknown states;
- public snapshot and nested objects contain no internal owner/fingerprint fields;
- event timestamps that tie still return deterministic order;
- disabled feature flag fails closed;
- unknown executor mode does not invoke any adapter.

## Two-session handoff

Use separate worktrees and branches. The handoff must include:

- absolute worktree path;
- immutable base commit;
- allowed and forbidden files;
- API assumptions and known unavailable endpoints;
- exact test/build gates;
- explicit instruction not to fabricate telemetry or mocks;
- commit/push approval boundary.

A frontend session should render `unavailable`, `blocked`, or `stale` when the backend contract is missing. It must not invent a backend response to make the UI look complete.

## MissionRun example

The MissionRun slice exposed three recurring hazards worth checking in future work:

1. cancel handlers can accidentally accept the current state as the expected state and therefore cancel terminal runs;
2. separate database calls for `queued → preparing → running → succeeded` create partial-commit races;
3. top-level response redaction is insufficient when the snapshot contains the internal field.

The durable fix is a shared transition state machine, an atomic dry-run persistence command, and recursive/public snapshot construction.
