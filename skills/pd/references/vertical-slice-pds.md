# Vertical-slice PDS reference

Reusable pattern for AI-assisted, single-user products that transform user-owned artifacts.

## Gate sequence

1. **G0 discovery:** create a clean target repo/worktree; inspect legacy source read-only; record exact schema, runtime versions, fixtures and WIP boundaries.
2. **G1 plan grill:** review SPEC/PLAN/Fleet; compile a full task envelope for every planned task before dispatch; classify and resolve BLOCKER/HIGH findings.
3. **Wave 1 contracts:** define canonical claims/evidence, contextual packages, state transitions, action envelopes, policy checks and threat fixtures.
4. **Wave 2 domain:** use strict RED → GREEN tests for value objects and guards before API/UI.
5. **Close every gate with evidence:** run focused tests, full suite, CLI validation, JSON/YAML parsing, `git diff --check`, then update STATE/CHECKPOINT/VERIFICATION.

## AI artifact model

- Canonical artifact = structured facts/claims/evidence; never a mutable text blob.
- Contextual output = immutable versioned package with source claim IDs, input/output hashes, prompt/model metadata and warnings.
- Missing facts become questions; inferred metrics, credentials or seniority are blocked.
- External effects require a human approval that references the exact package hash; dry-run proves zero provider/network calls.

## SQLite-first MVP

For a local/single-user first slice, SQLite is a valid source of truth when the domain is repository-decoupled:

- enable WAL, foreign keys and bounded busy timeout;
- keep transactions short and never hold them during an LLM/provider call;
- use FTS5 for search and JSON only for payloads/agent reports, not for core relational state;
- keep PDFs/DOCX outside the DB, storing metadata, safe paths and hashes;
- test idempotency, migration from a pre-existing DB, locking/retry behavior and artifact hash stability;
- defer PostgreSQL until multi-user access, multiple distributed writers, replicas or queue scale is a demonstrated requirement.

## PD CLI reconciliation

`pd validate --deep` checks its own textual conventions, not just semantic quality. A valid PDS should include:

- at least one real checkbox requirement in SPEC.md;
- a `.spec/<feature>/tests/` directory with a non-empty Python test file, even if canonical executable tests live at repository `tests/`;
- a literal `## Decisions` section in CONTEXT.md;
- parseable STATE.json and Fleet YAML.

If a manually authored PDS passes semantic review but fails these checks, adapt the documentation to the CLI's contract and rerun validation. Do not use `--force` to hide an unmet gate. If the CLI maintains stale internal state after manual PDS creation, record that mismatch explicitly and treat file-based evidence as authoritative only after independent parsing/validation.

## Evidence hygiene

- Fix malformed fixtures before using them as security evidence; e.g. literal `\\n` escapes are one physical line, not a multiline hostile prompt.
- Never absorb unrelated WIP from a legacy Git root. Use a new repo/worktree and a read-only adapter boundary.
- Delegated reports are leads; independently verify file existence, exact test commands, counts and commit/push status.
