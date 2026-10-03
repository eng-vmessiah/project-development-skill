# Executing authorized implementation waves without false closure

## Trigger

Use when a user authorizes a multi-task implementation plan and asks to continue through a wave, especially after expressing frustration with partial progress reports.

## Operating rule

A wave is not complete because one constituent change is green. Keep the wave active until every planned acceptance item is either:

1. implemented and tested;
2. explicitly blocked with evidence and a required user decision; or
3. intentionally descoped with explicit user approval.

Do not label a checkpoint, focused test run, or isolated commit as a completed wave when downstream acceptance gates remain.

## Subagent pattern

Use subagents for independent read-only analysis/review of disjoint concerns (for example concurrency vs. lease recovery). The parent owns integration. Convert every finding into a tracked item, then address findings in dependency order before final review.

## Wave closeout checklist

- Reconcile branch, plan and dirty files before editing.
- Red-first regression for each behavior change.
- Preserve one canonical writer for durable state; workers compute only.
- Test fault boundaries, not only happy paths: invalid CLI values, stale vs. live leases, partial commit/resume, missing events, duplicate/missing executor results.
- Run focused tests after each task.
- Run full suite, compile/lint, diff check and documentation validation once all wave items are implemented.
- Obtain independent review after all remediation, not only midway.
- Commit only the completed wave; record evidence and remaining blockers truthfully.

## Pitfall observed

Do not expose parallel execution merely by threading a CLI value into an executor. First prove: declarative wave barriers, dispatcher isolation, deterministic coordinator-only persistence, partial-batch resume, and expired-only lease recovery.

## Durable-event repair invariant

When a durable terminal report and its event are written through separate operations, treat recovery as a concurrency-sensitive contract, not a best-effort log append:

- Derive a repair event only from the persisted terminal report — never from an in-memory worker result.
- Put `check event absent → append event` behind one store-level lock/API such as `append_terminal_event_if_absent`.
- A no-op repair must not rewrite the snapshot, bump generation, timestamp, or event sequence.
- Route **both** resume repair and ordinary post-commit publication through the same idempotent primitive. Fixing only resume leaves a race where normal completion duplicates its event.
- Test: repeated repair, two concurrent repair callers, an existing non-terminal event for the task, and interleaving between normal completion and resume.

## Review-loop discipline

A final review can expose cross-path invariants that focused tests miss. Treat every `BLOCKED` finding as a reopened wave item: add a regression, remediate every equivalent production path, rerun the final review, and only then commit. Do not substitute a green full suite for this re-review.
