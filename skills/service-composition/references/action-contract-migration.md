# Action Contract Migration Notes

## Proven sequence

1. Choose one low-risk action (`validate_mission_plan`) before dispatch.
2. Add RED tests for envelope, bounded errors, audit, idempotency/replay, owner scope, and legacy compatibility.
3. Implement the action adapter while leaving the legacy route intact.
4. Add frontend wire types and a defensive normalizer.
5. Add owner-scoped audit read/query.
6. Add an idempotency table with a unique `(owner, action, key)` boundary and stored bounded response for replay.
7. Migrate write actions (`squad.create`, `squad.update`) using the same envelope.
8. Add `owner_hash` with an additive SQLite migration; update legacy routes to resolve the authenticated owner too.

## Durable pitfalls

- A shared SQLite test database makes fixed idempotency keys collide across full-suite runs. Use unique per-test keys or a narrow fixture reset seam; never weaken production uniqueness.
- Existing rows may predate a new ownership column. Check `PRAGMA table_info` and use `ALTER TABLE ... ADD COLUMN ... DEFAULT ...`; do not reset the database.
- If legacy create routes keep writing `owner-placeholder` while action update routes use the authenticated owner, valid compatibility tests fail with 404. Propagate `Request`/owner into legacy list/create/update adapters.
- `aiosqlite` query readers need `db.row_factory = aiosqlite.Row` before `dict(row)`.
- Do not add an unsafe action fallback that searches unowned/foreign rows; fix the legacy ownership write path instead.

## Verification evidence pattern

Record focused RED/GREEN counts, related legacy tests, full backend count, frontend build/lint, `py_compile`, `git diff --check`, and secret scan. Keep infrastructure warnings separate from changed-area failures.
