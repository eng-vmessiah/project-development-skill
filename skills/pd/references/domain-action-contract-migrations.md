# Domain Action Contract Migrations

Reusable reference for introducing an Agent-Native-style action contract into an established API.

## Goal

Make one domain operation reusable by UI, HTTP, agent tools, MCP, CLI and future transports without duplicating validation, policy, execution or audit behavior.

## Boundary selection

Prefer the smallest safe action first:

```text
read-only validation → draft mutation → approval → dispatch
```

Do not use a legacy route as the first action boundary if it combines:

- model prompt construction;
- model response parsing/fallback;
- persistence;
- conversation messages;
- status transitions;
- side effects.

Inventory the legacy flow separately and decide whether to retire, wrap, or leave it isolated.

## Minimal envelope

A first version should have bounded, explicit fields:

```json
{
  "action_id": "domain.operation",
  "schema_version": "1",
  "status": "succeeded|completed_with_errors|failed",
  "source": "http|ui|agent|mcp|cli|scheduler",
  "context": {
    "request_id": "safe-correlation-id",
    "actor_type": "human|agent|system",
    "actor_id": "safe-principal-id"
  },
  "result": {},
  "audit": {
    "recorded": true,
    "event_type": "action.completed"
  }
}
```

Do not include prompts, provider responses, credentials, cookies, raw stack traces, idempotency secrets or request fingerprints in the public envelope.

## Compatibility pattern

When the existing endpoint is consumed by a frontend or old tests:

```text
legacy endpoint (/preview) → legacy response shape
new action endpoint (/validate) → versioned envelope
```

Keep both paths temporarily. Change old tests to call the explicit compatibility path; never weaken the new contract to satisfy an old response assertion.

## RED tests

The first RED slice should prove:

- happy path returns action ID/version/status/source/result;
- invalid domain state returns stable machine-readable error code;
- supplied request ID propagates unchanged;
- actor type is resolved without exposing secrets;
- audit reports recorded only after durable persistence;
- dispatch remains disabled/false.

Run the RED file alone and confirm failure is a missing contract field, not syntax, fixture, import or environment failure.

## Frontend wire contract

Keep the transport contract explicit at the frontend boundary instead of typing the raw response inline in a page. Define a domain normalizer that:

- accepts only the expected `action_id` and `schema_version`;
- rejects missing/invalid fields with `null` or a bounded error;
- converts backend `snake_case` to frontend `camelCase` in one place;
- preserves unknown nested details as `unknown`, not `any`;
- rejects unsafe states such as `dispatch: true` when the phase is read-only.

Test the normalizer independently before wiring it into React. This provides a stable seam for later UI, Hermes and MCP adapters without coupling the page to backend serialization.

## Durable audit

Use an additive table or existing event seam with bounded fields:

```text
action_id
schema_version
status
actor_type
actor_id
source
request_id
resource_id
redacted_details
created_at
```

The action should not return `recorded: true` until the insert/commit succeeds. A best-effort operational logger is not sufficient evidence for a control-plane audit contract.

## Owner-scoped audit read/query

When audit evidence needs to be displayed in a cockpit, add a read-only query contract rather than exposing the raw table:

```text
GET /api/action-audit?action_id=&resource_id=&limit=1..100
GET /api/action-audit/{resource_id}?limit=1..100
```

Requirements:

- filter by authenticated/derived `owner_hash` in SQL, not after retrieval;
- use bounded pagination (`1..100` or the host project's explicit limit);
- return only safe fields (`action_id`, version, status, actor/source, request ID, resource ID, redacted details, timestamp);
- never return `owner_hash`, credentials, cookies, idempotency keys, fingerprints, prompts or raw provider errors;
- test same-owner list/resource filters and cross-owner exclusion with a deterministic fixture.

For SQLite migrations, `CREATE TABLE IF NOT EXISTS` does not add columns to an existing table. Add an additive `PRAGMA table_info(...)` check and `ALTER TABLE ... ADD COLUMN ... DEFAULT ...` migration. When converting query rows with `dict(row)`, set `db.row_factory = aiosqlite.Row` on that connection; otherwise the query can pass SQL execution but fail during serialization.

## GREEN order

1. Add schema/table migration or `CREATE TABLE IF NOT EXISTS` compatible with the local persistence model.
2. Add a narrow audit persistence function.
3. Extract a shared domain validation result shape.
4. Add the versioned action route.
5. Keep the legacy route adapter unchanged in its public shape.
6. Add an owner-scoped, read-only audit query and redaction tests when the audit is user-visible.
7. Run RED tests.
8. Run the focused legacy regression slice.
9. Run the complete backend/frontend quality gates.
10. Review the diff for secrets, accidental dispatch, raw errors and route ownership.

## Checkpoint evidence

Record:

- implementation branch/worktree;
- RED commit and failure reason;
- GREEN commit;
- focused test count;
- full-suite count and warnings;
- compatibility route retained;
- deferred agent/MCP/dispatch surfaces;
- next unblocked action.

## Common pitfalls

- Reusing one handler for legacy and new response shapes.
- Adding an envelope without versioning it.
- Returning free-form error strings instead of codes plus bounded messages.
- Claiming audit success from `log_event` that swallows exceptions.
- Exposing the new action to Hermes/MCP before an explicit allowlist/policy exists.
- Changing dispatch behavior while implementing a read-only validation action.
- Treating a registered branch name as proof that a worktree path is valid; verify with `git worktree list` and `git status`.
- Reporting only focused tests and skipping the full suite.
