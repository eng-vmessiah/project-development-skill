# Multi-wave closeout and merge readiness

Use this after a plan was implemented by several fresh subagents or waves.

## Three separate statuses

- **Implementation complete:** planned code/tests/docs exist.
- **Verification complete:** fresh commands and independent reviews pass for the current tree.
- **Merge-ready:** scope is committed, branch integration is understood, delivery is approved, and release/deployment gates are satisfied.

Never collapse these into a single `PASS`.

## Inventory before merge

```bash
git status --short --branch
git branch -vv
git log --oneline --decorate --graph --all -12
git diff --stat
# include untracked paths in the inventory
git ls-files --others --exclude-standard
```

Group the inventory into:

1. existing files modified;
2. new implementation modules;
3. new tests;
4. documentation/spec/state;
5. generated artifacts;
6. unrelated or accidental changes.

A feature that began in one entrypoint may legitimately touch many files after a multi-wave plan. Verify ownership from the plan; do not guess from the original user wording.

## Evidence rules

- A subagent's claim is a lead. Verify the file, exact test path, exit status, and current output locally.
- Re-run the full suite after the last fix and again on the exact commit intended for merge.
- Keep a fresh evidence file with current count, checker output, artifact digests, known residuals, and the decision (`READY`, `PARTIAL`, or `NOT READY`).
- Label historical/intermediate counts as historical; never call an old count fresh.
- A human approval gate must contain an explicit owner, identity, scope, evidence/artifact digest, freshness, and decision. Tests cannot synthesize it.

## Delivery boundaries

Do not commit, push, rebase, merge, or discard dirty worktree changes implicitly. First obtain delivery scope when the session produced broad subagent WIP. Prefer logical commits by wave or contract boundary; include tests and evidence with the implementation they verify.

Before integrating with `main`:

1. commit or deliberately isolate all intended changes;
2. confirm base branch and ahead/behind state;
3. rebase/merge only on a clean, owned worktree;
4. resolve conflicts by preserving both intents, not by taking an entire file from one side;
5. rerun gates on the integrated commit;
6. distinguish an experimental/local merge from an operational release.

## Common final verdicts

- **Ready to merge, not release:** committed and verified, but external providers/sandbox/deployment remain disabled.
- **Not ready / partial:** implementation and local evidence exist, but worktree is dirty, integration is uncommitted, or human/release gates are pending.
- **Blocked:** a required test/review/integration gate fails.
