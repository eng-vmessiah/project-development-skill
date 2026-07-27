# Vertical Slice Execution Checklist

Use this when a PD project combines a new repository, a legacy JSON adapter, SQLite, and AI-assisted domain logic.

## G0 — boundary and evidence

- Confirm the target repo is isolated and clean before source edits.
- If a legacy path resolves to a broader or dirty Git root, do not absorb its WIP.
- Inspect the real legacy payload with redaction; record count and field shape.
- Create deterministic fixtures, including hostile input as data.
- Ensure fixture files contain actual line breaks; test their parser.

## G1 — plan grill

- Read SPEC, PLAN, CONTEXT, DECISIONS, STATE, and CHECKPOINT.
- Compile a full envelope for every task: role, dependencies, paths, inputs, outputs, acceptance, validation, blockers.
- Review domain truth, human gates, security, idempotency, rollback, and non-goals.
- Run the validator after satisfying its exact textual contract; never use force to hide missing evidence.

## Validator reconciliation

The generic PD validator currently checks:

- `SPEC.md`, `PLAN.md`, `CONTEXT.md`, `STATE.md`, `STATE.json`;
- checkbox-style requirements in `SPEC.md`;
- at least one task checkbox in `PLAN.md`;
- non-trivial `VERIFICATION.md`;
- at least one non-empty `.py` file in `.spec/<feature>/tests/`;
- a literal `## Decisions` heading and multiple bullet decisions in `CONTEXT.md`.

Keep repository-root executable tests and feature-spec validator fixtures separate but synchronized.

## SQLite gate

Do not mark a migration gate complete merely because `CREATE TABLE IF NOT EXISTS` passes on a fresh database. If the plan promises Alembic or additive migration, execute the migration against an existing schema and verify preservation of data. Keep WAL, foreign keys, busy timeout, FTS5, backup/restore, and lock-contention evidence separate.

## Ingestion gate

Test all of:

1. same-ID rerun is idempotent;
2. different IDs with the same fingerprint deduplicate;
3. raw payload is preserved in append-only snapshots;
4. normalized rows remain searchable;
5. contact/PII fields are redacted in reports and logs.

## Continuation and closeout

When the user says `continuar`, a checkpoint is not a conversational stop. After updating state, start the next unblocked RED test or inspection in the same turn. Before a checkpoint is publishable, run the focused test, full suite, `pd validate --deep`, `git diff --check`, and verify the pushed branch status.
