# Action-contract persistence and replay reference

Reusable implementation notes for FastAPI + SQLite action contracts.

## Contract migration

- Keep the legacy endpoint and the versioned action endpoint separate when their response shapes differ.
- Action envelope should carry stable `action_id`, `schema_version`, status, source/context, bounded result, and audit metadata.
- Do not report `audit.recorded=true` until a durable insert succeeds.

## Audit read boundary

Use owner-scoped queries as the default predicate. Expose only bounded, read-only fields:

- action ID and schema version;
- status, actor type, source, request ID;
- resource ID, details, timestamp.

Do not expose owner hashes, idempotency keys, prompts, tokens, raw model output, or authorization material. Bound `limit` at the API layer and test action/resource filters plus cross-owner isolation.

## Idempotency

For a sensitive/read-only action, a key should be scoped by:

```text
(owner_hash, action_id, idempotency_key)
```

Persist the resource ID, audit ID, and a bounded serialized response. Same resource replays without inserting a second execution audit event. The same key against another resource returns a stable conflict (normally HTTP 409). Mark replay in the response (`replayed=true`, `action.replayed`) without changing the original result or audit ID.

## SQLite migration and test hygiene

`CREATE TABLE IF NOT EXISTS` does not add new columns to an existing table. After changing a local schema:

1. inspect with `PRAGMA table_info(...)`;
2. add an additive `ALTER TABLE` migration with a safe default;
3. run tests against an existing database shape when possible;
4. never reset/delete a shared database as a test workaround.

Shared SQLite test state can make fixed idempotency keys collide across test runs. Derive keys from unique resource IDs or use an explicit isolated database fixture. Treat a failure caused by stale test state as a fixture problem only after verifying the production query/constraint behavior.
