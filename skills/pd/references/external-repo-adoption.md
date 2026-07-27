# External Repository Adoption Checklist

Use this reference when an external repository may become a future dependency, provider, memory layer, MCP server, or architectural source.

## Audit record

Capture:

- repository URL and pinned revision;
- license and contribution/security posture;
- runtime and package manager requirements;
- architecture and process topology;
- integration contracts (CLI, MCP, HTTP, SDK, plugin);
- data stores and migration behavior;
- network/provider/API-key paths;
- tests and which ones were actually run;
- upstream claims that remain unverified;
- operational surface (services, cron, admin, ports, backups);
- install blockers and their exact fix, without turning setup failures into permanent tool prohibitions.

## PDS branch package

For a future adoption plan, create an isolated branch/worktree from a clean base and include:

```text
.spec/<feature>/README.md
.spec/<feature>/SPEC.md
.spec/<feature>/RESEARCH.md
.spec/<feature>/CONTEXT.md
.spec/<feature>/PLAN.md
.spec/<feature>/STATE.md
.spec/<feature>/STATE.json
.spec/<feature>/CHECKPOINT.md
.spec/<feature>/VERIFICATION.md
.spec/<feature>/DECISIONS.md
```

Keep implementation status honest: `planned`/`not_started` until code and fresh evidence exist. Separate completed audit evidence from deferred verification.

## Safe first spike

1. Pin the upstream revision.
2. Install runtime in a disposable/user-local toolchain.
3. Use a dedicated data directory outside active agent/config/vault paths.
4. Build a sanitized fixture set with stable source IDs and expected claims.
5. Establish a baseline against the current system before importing into the candidate.
6. Run candidate in read-only/shadow mode.
7. Test provenance, citations, stale data, contradictions, missing answers, scope isolation and redaction.
8. Test export, delete, rebuild and rollback.
9. Integrate through the narrowest stable boundary (prefer local stdio MCP or a small adapter).
10. Use a fresh-eyes review before connecting active runtime or enabling automation.

## Memory/knowledge-specific rules

- Preserve the existing human-readable source of truth during evaluation.
- Treat the candidate as an index/brain, not an authority, until proven.
- Do not automatically write back to identity, user profile or daily notes.
- Compare one candidate at a time; do not run competing memory providers in the same active context.
- Record which providers receive embeddings/synthesis text and where data is retained.
- Make citations and explicit gaps part of the response contract.
- Do not import a whole private vault before a small sanitized evaluation passes.

## Delivery boundary

Commit and push the documentation branch if requested/allowed, but do not merge, deploy, restart services, add secrets, or alter the active agent runtime merely because the plan is complete. Adoption requires a separate approval gate backed by evaluation and rollback evidence.
