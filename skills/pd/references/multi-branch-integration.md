# Multi-Branch Integration — Release Candidate Assembly

## When to Use

Multiple feature branches finished in isolation and need to become one coherent release candidate before `main`. Not for daily development — only when you have 2+ independent branches that must land together.

## Principles

1. **One integration worktree.** A standalone `git worktree` is the only place merges happen. Source branches stay untouched.
2. **Dependency order.** Merge in dependency order (e.g. foundation → tooling → product). A later branch preserves prior branch's behavior.
3. **Provenance, not squash.** Every merge is `--no-ff` with a descriptive message. Resolution commits name preserved intents.
4. **Phase isolation.** Each branch is validated immediately after its merge. A later branch never masks a prior branch's regression.
5. **Migration canon.** Final migration numbers are assigned once in the integration branch. No feature branch retains a duplicate version.

## Workflow

### 0. Prepare

```bash
# From the main repo
git fetch --all --prune
git worktree add ../repo-integration integrate/release-candidate
cd ../repo-integration
```

Record source heads, verify clean worktrees, confirm `main` base commit.

### 1. For each candidate branch (in order)

```bash
# Merge with provenance
git merge --no-ff feature/X -m "merge(area): integrate feature X"

# Resolve conflicts — never pick an entire side blindly.
# Use :1/:2/:3 to inspect each version:
git show :1:<path>  # merge base
git show :2:<path>  # integration (ours)
git show :3:<path>  # incoming (theirs)

# Preserve BOTH intents — the resolution should keep behavior
# from both sides when they touch different concerns in the
# same file.
```

### Selective file exclusion during merge

When a source branch contains files that MUST NOT enter the product tree (development artifacts, generated outputs, session files, credentials, or alternate product surfaces):

1. Merge the branch normally so provenance is preserved.
2. Inspect the incoming paths against the target repository's allowlist.
3. Remove only the explicitly excluded paths before committing:

```bash
git rm -r -- path/to/excluded-artifact path/to/generated-output
git add -A
git commit
```

Do NOT use `git merge --no-commit` + cherry-pick as a substitute — that loses provenance. The merge commit records the branch origin; the removal commit records the exclusion rationale. Both are auditable.

If an excluded path conflicts during merge, resolve the source-file conflict first, then remove the excluded artifact and record the rationale in the merge message or integration summary:

```bash
git merge --no-ff feature/name -m "merge(area): integrate feature (exclude generated artifacts)"
git rm -r -- path/to/excluded-artifact
git commit --amend --no-edit   # or commit separately
```

### Stash discipline during merge

If you need to stash plan/doc changes before a merge:

```bash
git stash -- plans/README.md        # stash only the doc changes
git merge --no-ff feature/X         # may succeed or fail
git stash pop                        # MUST check this succeeded
```

**Pitfall:** If the merge fails, `git stash pop` does NOT run automatically. The stash remains and subsequent `git checkout --ours` or `git add -A` will NOT restore it. After resolving conflicts and committing the merge, run `git stash pop` explicitly. Verify with `git stash list` — an empty list means all stashes were popped.

### Validate immediately

Use the candidate branch's canonical focused tests, typecheck, build, and smoke commands. Do not copy commands from another repository into the integration guide. Record the exact commands and results in the integration summary:

```bash
<focused-test-command>
<typecheck-command>
<secondary-component-test-command>
<feature-smoke-command>
git diff --check main...HEAD
```

Green → proceed. Red → fix before advancing to the next branch.

### 3. Migration ledger

Maintain one append-only migration sequence. Use a reserved range per source branch:

| Range | Owner |
|-------|-------|
| v<range-1> | Foundation or shared infrastructure |
| v<range-2> | Product surface A |
| v<range-3> | Product surface B |

Renumber during the merge resolution, update migration descriptions, and update any version-asserting tests.

### 4. Gap documentation

When a feature intentionally defers a sub-task or known limitation, **document it visibly in the plan file** (design.md, resumo.md, or checkpoints.md). Do not rely on memory or inline TODO comments. The gap must be findable by anyone reviewing the integration later.

Format:
```markdown
## Pendência pós-merge

O campo `X` não é populado. Para implementar:
1. Criar storage AsyncLocalStorage
2. Popular nos pontos de entrada
3. Referenciar nos call sites

O schema já aceita o campo como opcional — pode ser feito em ciclo posterior sem quebrar compatibilidade.
```

### 5. Comprehensive integration summary

After all branches are merged and validated, produce a **narrative summary** document that covers:

- **Per-component:** what was built, what changed, key files, rationale
- **Architecture decisions:** why certain approaches were chosen
- **Gates:** test counts, typecheck, smoke results
- **Review findings:** blocking issues (with severity), observations, preserved contracts

This goes beyond verification output — it is a handoff document for anyone reviewing the integration later. Save it as `plans/active/<integration-name>/resumo-geral.md` in the integration worktree.

### 6. Release candidate gates

- Full backend suite + typecheck
- Applicable hermetic smokes
- `git diff --check main...HEAD`
- Independent integration review (check migration monotonicity, lost telemetry/correlation, lifecycle hooks, authorization bypass, artifacts/credentials in diff, branch duplication)
- Only then: push + PR (with explicit approval)

## Commit vs Push clarity

After committing, always state explicitly whether the commit was also pushed. Saying "committed" without "and pushed" means the remote branch is unchanged. If the user checks the remote and doesn't find the commit, they will (rightly) ask. Use:
- "Commit `abc123` — local apenas" (se não fez push)
- "Commit `abc123` — push feito" (se enviou)
