# Execution and closeout discipline

Use this reference when the user asks to register a plan and act on it, continue a standing plan, or finish an implementation wave.

## Required behavior

1. Treat explicit execution language (`implementar`, `atuar nele`, `continuar`, `seguir`, `finalizar o plano`) as authorization to start the next unlocked task now, not as a request for another plan recap.
2. Register the plan/state artifacts before source edits, then execute the first dependency-ready slice in the same turn.
3. After each slice, maintain separate labels:
   - **implemented**: code/artifacts exist;
   - **verified**: fresh commands passed against the current workspace;
   - **review pending**: independent/fresh-eyes review has not run or has unresolved findings;
   - **deferred**: intentionally outside the current slice;
   - **blocked**: cannot proceed without a decision, dependency, or authorization.
4. Do not mark the overall verification/closeout gate complete solely because focused tests or the full suite pass. Review and reconciliation are separate gates.
5. If the user authorized continued execution, do not stop at a checkpoint summary. Start the next unblocked task unless a genuine blocker or explicit pause exists.
6. Do not commit, push, merge, deploy, or publish unless that delivery stage was explicitly requested. A dirty worktree can be an intentional implementation boundary and must be reported accurately.

## Minimum checkpoint content

Record the exact next task, current branch/worktree boundary, changed paths, fresh verification commands and counts, unresolved review status, and the resumable command or gate. Never infer a score, status, deduplication count, or completion state that the evidence does not provide.

## Common failure

A report that says “implemented and verified” while its own body says “independent review pending” is internally inconsistent. Use `implemented + tests verified + review pending + overall partial` until the review gate and remediation loop are complete.
