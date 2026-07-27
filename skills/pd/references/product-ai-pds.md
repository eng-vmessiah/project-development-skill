# Product/AI PDS Reference

Reusable pattern for a single-user, AI-assisted product that transforms user-owned artifacts and may eventually perform external actions.

## 1. Domain split

Use three layers:

```text
Canonical artifact
  ├── claims/facts
  ├── evidence/source references
  ├── confirmation status
  └── version history

Canonical refinement
  └── diagnostics, diffs, questions, accepted edits

Contextual composition
  └── target requirements → evidence mapping → strategy → versioned package
```

The canonical refinement layer improves the source of truth. The contextual composition layer adapts a version for one target. Never let contextual composition silently rewrite the canonical artifact.

## 2. Minimum AI output contract

```json
{
  "status": "completed|blocked|failed",
  "output": {},
  "source_claim_ids": [],
  "evidence": [],
  "confidence": 0.0,
  "warnings": [],
  "questions": [],
  "prompt_version": "domain.operation.v1",
  "model": "provider/model",
  "input_hash": "sha256",
  "cost_usd": 0.0
}
```

No free-form model output should cross a domain mutation or external-action boundary without schema validation and policy checks.

## 3. Vertical slice pattern

Prefer this order:

1. fixture with real-shaped input;
2. ingestion/normalization;
3. requirement or target extraction;
4. evidence mapping;
5. contextual composition;
6. factual/policy review;
7. immutable package/artifact;
8. Inbox or human review;
9. approval dry-run;
10. only later, real external side effect.

The slice should prove the value loop and the trust model before investing in dashboards, many integrations, or autonomous agents.

## 4. SQLite-first MVP decision

For a single-user/local MVP, SQLite is usually the lowest-risk persistence choice:

- use WAL, foreign keys, and a busy timeout;
- keep transactions short and never hold one across an LLM/network call;
- use SQLAlchemy/Alembic or an equivalent migration layer;
- use FTS5 for textual search;
- keep binaries in object/file storage and persist metadata/hashes in SQLite;
- use repository interfaces so the domain is not coupled to SQLite;
- bound writers/workers; do not treat SQLite as a distributed queue;
- record explicit migration triggers to PostgreSQL: multiple real users, replicated instances, distributed writers, remote multi-tenant access, or proven scale need.

Do not introduce PostgreSQL, Redis, Temporal, or n8n merely because they are available. Add them when a measured constraint requires them.

## 5. PD gates for AI + external actions

- **G0 discovery:** audit target repo/status, legacy schema, fixtures, toolchain, and data boundaries read-only.
- **G1 plan grill:** review requirements, non-goals, contracts, threat model, ownership, and no-code boundary.
- **Domain gate:** state transitions, idempotency, versioning, audit schema, and migrations pass tests.
- **Safety gate:** adversarial inputs, prompt injection, unsupported facts, PII leakage, and package drift are blocked.
- **Human gate:** user sees exact artifact, recipient, body, attachments, warnings, and package hash before approval.
- **Evidence gate:** normal, blocked, retry, resume, and dry-run paths have fresh command output.

Subagent reports are leads, not proof. The orchestrator independently verifies critical files, test paths, hashes, and command results.

## 6. Common product traps

- Rewriting the whole canonical artifact in one opaque operation.
- One score hiding requirement coverage, confidence, and missing evidence.
- Turning every target keyword into a claimed skill.
- Allowing a contextual version to mutate the canonical source.
- Building a dashboard before proving the action loop.
- Sending an unversioned "current" artifact after approval.
- Allowing an agent to send external messages directly.
- Treating rejection as deletion instead of an auditable decision.
