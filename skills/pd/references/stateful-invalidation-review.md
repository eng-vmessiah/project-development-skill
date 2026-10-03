# Stateful task invalidation review

Use this checklist when a Fleet/run store gains a task-status invalidation or public mutation API.

## Adversarial sequence

1. Create a task and acquire a lease.
2. Invalidate the task to a terminal status.
3. Attempt stale `commit`, `renew`, and `use`; each must fail closed.
4. Attempt single and batch reclaim; both must reject terminal tasks.
5. Attempt malformed and cross-boundary tokens, including duplicate-commit paths; all must fail before idempotent success.
6. Attempt to invalidate a task already present in reports; the snapshot must remain unchanged.

## Invariants to compare

- snapshot fields unchanged except the intentional status/lease invalidation;
- no new or incremented attempt;
- no report/event/checksum corruption;
- no dispatcher call when governance input is absent, malformed, or hostile;
- no external/runtime behavior inferred from local verification.

## Evidence standard

Record targeted test counts, full-suite result, compile/syntax result, documentation validation, diff check, and local example result. Keep production/release/live-runtime readiness as separate gates. No credentials, tokens, or secrets belong in the record; redact them.
