---
name: pd
description: "Bomb-proof development pipeline: brainstorm → spec → plan → code → test → review. Master orchestrator for software projects."
version: 1.2.0
license: MIT
metadata:
  hermes:
    tags: [project-development, pipeline, orchestration, bomb-proof, workflow]
    related_skills: [writing-plans, test-driven-development, requesting-code-review, subagent-driven-development, debugging-discipline, spike]
argument-hint: "What feature or project needs the full pipeline?"
---

# Project Development (PD)

PD is a gated workflow for turning an idea into a verified, reviewable change. It is intentionally strict about discovery, planning, evidence, and recovery from failure.

## Prime directive

```text
NO SPECIFICATION + PLAN + .spec STATE, NO CODE
```

Every PD-managed change MUST have a `.spec/<feature>/` control plane before implementation. A repository's native planning files may coexist, but they do not replace the PD control plane. Link them from `.spec/<feature>/CONTEXT.md` when necessary.

## When to use

Use PD for:

- new projects, features, integrations, and multi-file refactors;
- work requiring research, architecture decisions, or multiple sessions;
- changes crossing backend/frontend/CLI/provider/security boundaries;
- external repository adoption or supervised agent fleets.

For a one-turn typo fix, obvious rename, or missing import, the full pipeline may be skipped.

## Mandatory artifacts

Create this minimum control plane before coding:

```text
.spec/<feature>/
├── SPEC.md            # problem, requirements, non-goals, success criteria
├── PLAN.md            # ordered tasks, dependencies, validation commands
├── CONTEXT.md         # decisions, constraints, assumptions
├── STATE.md           # human-readable progress
└── STATE.json         # machine-readable progress
```

Create `README.md`, a timestamped `CHECKPOINT-<YYYYMMDD-HHMM>.md`, and `VERIFICATION.md` during the planning/verification gates before delivery. Add `RESEARCH.md`, `DECISIONS.md`, task files, and `tests/` when the change needs them. The exact artifact contract and templates are in `references/create-implementation-plan.md` and `references/writing-plans.md`.

### Evidence and synthesis are separate artifacts

Keep the raw findings out of the synthesized context:

| Artifact | Nature | Holds |
|---|---|---|
| `DISCOVERY.md` | evidence | what was found in the repo, vault, issues and docs, with provenance |
| `GRILLING.md` | evidence | questions asked, answers, objections, **explicit vetoes**, assumptions |
| `CONTEXT.md` | synthesis | decisions, constraints, risks, read from the two above |

A wrong synthesis must stay traceable to its raw input, so never fold the interview transcript into `CONTEXT.md` and delete the source. `GRILLING.md` is also the only place that records what the owner refused; without it the plan re-proposes a rejected idea a few weeks later.

## Work units (do not invent a level)

| Unit | Is | Decision owner |
|---|---|---|
| spec | isolation unit (one worktree per spec) | orchestrator |
| stage | a pipeline gate with its own artifact (G0…G7) | gate owner |
| wave | batch of tasks that may run together | scheduler |
| task | the contract: acceptance and evidence | orchestrator |
| session | the worker that receives commands and emits events | orchestrator |
| mission | what is approved, measured and closed | human |

Check the method's own vocabulary before naming a new level: a "round" invented alongside an existing gate/wave creates a parallel vocabulary and gets rejected on sight. Parallelism is computed, never chosen by the model: tasks run together only when their write sets are disjoint and they share no exclusive resource (migration, fixed port, state file, lockfile, integration branch). Integration is a queue, so a shared branch merges one wave at a time and the merged state is revalidated before the wave is called closed.

## Verifiable spec and delta

Write requirements so a machine can check them:

```markdown
### Requirement: <name> SHALL <behaviour>
One or two normative sentences.

#### Scenario: <name>
- WHEN <condition>
- THEN <observable result>
```

Each `Scenario` becomes one acceptance line in the plan and one check in the executor. A requirement with no scenario is untestable; a scenario with no `THEN` is prose. Validate the artifact before execution (`pd validate`, `isis spec validate`, or an `openspec validate` style checker): missing narrative, `WHEN` without `THEN`, and a delta without its section are rejections, not warnings.

For changes to a living system, do not write a spec that dies with the mission: keep a living spec per domain and record the mission's proposal as a delta (`ADDED` / `MODIFIED` / `REMOVED` / `RENAMED`), applied to the living spec when the mission closes.

## Pipeline gates

```text
G0 intake/worktree
  → G1 discovery and approved SPEC
  → G2 PLAN + dependencies + .spec state
  → G3 structure and task contracts
  → G4 implementation
  → G5 tests and debugging
  → G6 fresh-eyes review and verification
  → G7 delivery approval (commit/push/PR/deploy)
```

Do not silently cross a gate. A checkpoint records progress; it does not make an unfinished gate complete.

## Phase 0 — Intake and worktree

1. Inspect the repository, native conventions, branch/base, and current `git status`.
2. Preserve unrelated WIP. Never reset, clean, stash, commit, push, merge, or deploy implicitly.
3. Use an isolated worktree for risky, long-running, or parallel work.
4. Record the exact repository path, branch, base commit, and forbidden side effects in `.spec/<feature>/CONTEXT.md`.

## Phase 1 — Discovery and specification

1. Explore relevant code, tests, docs, and runtime boundaries.
2. Ask one decision question at a time when product or architecture choices remain open.
3. Compare 2–3 approaches and record trade-offs.
4. Write `SPEC.md` with:
   - problem statement;
   - requirements as checkable items;
   - non-goals;
   - constraints and risks;
   - recommended approach;
   - success criteria;
   - explicit external-effect policy.
5. Do not begin implementation until the specification is approved or the user explicitly authorizes proceeding with a clearly marked draft.

## Phase 2 — Planning

Write bite-sized tasks in `PLAN.md`. Every task must declare:

- objective and exact paths;
- dependencies and inputs;
- allowed and forbidden side effects;
- acceptance criteria;
- validation command;
- blocked conditions;
- rollback or recovery path when applicable.

Tasks in the same wave must be independent and have non-overlapping write ownership. A plan is not executable merely because it lists filenames; it must contain complete task contracts.

### Split by read-set, not by folder

A task's boundary is what it must read, not where the files live: two tasks that need the same context belong in one node; two tasks in the same folder that read disjoint context can run in parallel. Draw an edge only when one task consumes another's output; otherwise mark them parallel. This keeps each worker's context small and makes the write-set rule checkable.

### Deterministic steps are code

If a step has exactly one correct answer — merge, sort, dedupe, count, compare — implement it as code, not as a model call or a subagent. Model calls are for judgment; routing a deterministic step through an agent adds cost and a failure mode without adding information.

### The plan file is parsed by machine

`PLAN.md` is read by tooling (`pd`, or a repo importer such as `isis plan import --from-pd`), so two shapes are contracts and everything else is dropped in silence:

```text
## Wave <text>                        # ^## (Wave .+)$
- [ ] **T-123 · title** — objective   # needs " · " after the id and an em dash separator
```

A heading written `## Stage 3`, or a task separated by `-` instead of `—`, parses to nothing and the importer exits 0. **An unrecognized heading is worse than dropped when it sits between waves:** the parser keeps the previous wave open and silently absorbs the tasks under the odd heading into it, so the plan counts right while the tasks belong to a wave they were never in. Test the odd heading in BOTH positions — before any wave and after a valid one.

After editing, compare both counts before believing it landed:

```bash
isis plan import --from-pd PLAN.md --dry-run --json | python3 -c 'import json,sys; d=json.load(sys.stdin); print(sum(len(w["tasks"]) for w in d["waves"]))'
grep -cE '^- \[[ x]\] \*\*T-[0-9]{3}' PLAN.md
```

**A task id cited in prose is counted as a task by the boundary ruler.** The importer reads task *lines*, but the spec×plan reconciliation typically scans `T-[0-9]{3}` anywhere in the file — so writing "removing T-902" inside another task's description makes the spec count one higher and turns the boundary contract red for a reason that has nothing to do with the change. Keep task ids out of prose (say "remove the task" instead).

**A test that pins the total should pin a floor, not an equality.** `assert expected_tasks == N` breaks on every legitimate plan growth, and the failure lands in whichever commit happens to close the wave — so the count gets bumped reflexively, which is exactly how a deletion later passes unnoticed. Assert `expected_tasks >= N` with the reason, and let the strict importer (`unknown_heading`/`task_outside_wave`) be the thing that catches silent loss.

### Checkbox is a mirror, state is the truth

`STATE.json`'s task list is the completed set; the plan total comes from `PLAN.md`. Reconcile in classes with a script, never by hand:

- completed in state, checkbox open → fixable, mark it;
- checkbox closed, task absent from state → conflict, stop and investigate;
- task in state, absent from plan → orphan, stop;
- open checkbox and absent from state → pending, **not** a divergence.

Report the classes separately; collapsing them into "plan has N and state has M" hides which side is wrong.

For larger efforts, use the fleet and wave references:

- `references/fleet-orchestration.md`
- `references/fleet-orchestration-closeout.md`
- `references/fleet-hardening-contracts.md`
- `references/multi-wave-closeout.md`

## Phase 3 — Structure

Create `.spec/<feature>/` and initialize `STATE.md` plus valid `STATE.json` before touching product source. Add task files or `tests/` when the plan requires them.

Validate the planning artifacts themselves. Do not use `--force` to hide missing requirements, stale state, malformed JSON, or a missing test structure. The PD CLI is optional support tooling; `.spec` is mandatory even when the CLI is unavailable.

## Phase 4 — Implementation

For each task:

1. Read the current `SPEC.md`, `PLAN.md`, `CONTEXT.md`, and `STATE`.
2. Mark exactly one task `in_progress`.
3. Implement only the task's allowed scope.
4. Run its focused validation.
5. Record evidence, files, and outcome in the task/checkpoint state.
6. Mark it complete only after the validation succeeds.

Use fresh contexts for independent workers. The orchestrator owns dependencies, state, blockers, retries, and evidence; workers do not self-authorize unrelated work.

### Failure, recovery, and retry policy

A failed task is not permission to skip forward.

1. Preserve the failure output and mark the task `failed` when the task itself failed, or `blocked` when an external prerequisite/policy prevents execution.
2. Investigate the root cause before changing code. Distinguish implementation defects from environment/provider failures.
3. Create a remediation attempt in the timestamped checkpoint or task file with the hypothesis, change scope, and validation command.
4. Retry only a `failed` task whose error is classified retryable and whose `max_attempts` allows another attempt. A blocked task requires the blocker to be resolved and an explicit transition back to `ready`.
5. Record each attempt, result, and evidence. Use a bounded retry policy with an explicit `max_attempts`; do not loop indefinitely.
6. If the retry fails or attempts are exhausted, stop and escalate with the exact blocker and rollback path, unless the user authorizes another strategy.
7. Release the next task only when its dependencies are complete. Independent tasks may continue; every dependent task remains blocked until the failed dependency is green.
8. Never mark a failed or blocked task complete because a later task happened to pass.

See `references/fleet-orchestration.md` for DAG scheduling and the repository's debugging skill for root-cause investigation, bounded retries, and rollback. The task contract's `retry_policy` is authoritative: use an explicit `max_attempts`, classify retryable errors, and record every attempt. A blocked task is not automatically retryable; resolve its prerequisite and transition it back to `ready` first.

### Rulings, not stalls

Inside an approved wave, decide instead of pausing for permission, and record every judgment call:

```text
Ruling: <what was decided> — <why> — <cost if wrong>
```

Stop only for: an irreversible or destructive action; a security-sensitive action; an effect outside the worktree (merge, push to a shared branch, publish); or a plan so broken that every path is a guess. Everything else is a ruling with a recorded cost. A worker parked on a question burns the whole window and buys nothing.

## Phase 5 — Testing and debugging

Use RED → GREEN → REFACTOR for code changes:

1. Write a focused failing test for the required behavior.
2. Confirm it fails for the intended reason.
3. Implement the smallest change.
4. Confirm the focused test passes.
5. Run the relevant regression suite, then the full canonical suite.

Cover the highest-risk boundaries: response contracts, persistence/migrations, idempotency, ownership, rollback, malformed inputs, external-effect suppression, and call-site completeness. Use `references/cross-boundary-tdd.md`, `references/action-contract-persistence.md`, and `references/domain-action-contract-migrations.md` where relevant.

For failures, follow root-cause investigation rather than symptom fixes. Record unrelated provider or environment failures separately; never convert an incomplete suite into a green result.

## Phase 6 — Review and verification

Completion claims require fresh evidence from the current workspace.

Verify separately:

- requirement coverage against `SPEC.md`;
- decision coverage against `CONTEXT.md`;
- task/dependency state against `PLAN.md` and `STATE`;
- focused tests and full suite;
- lint, typecheck, build, and CLI probes when applicable;
- security scans and secret/path checks;
- changed and untracked paths;
- clean or intentionally documented worktree state.

Load `requesting-code-review` for independent fresh-eyes review. For non-trivial changes, use separate standards/quality and specification-compliance axes. Reviewer reports are leads until independently verified.

Write `VERIFICATION.md` with `PASS`, `PARTIAL`, `BLOCKED`, or `DEFERRED` per requirement. After an accepted result, record the rule it proved — in the plan, a skill, or the repo notes — so the next run starts from it instead of rediscovering it. Do not claim merge-ready or operationally released when provider, sandbox, human-approval, deployment, or external-dispatch gates remain unverified.

Detailed closeout guidance: `references/phase-closeout.md` and `references/multi-wave-closeout.md`.

## Phase 7 — Delivery

Commit, push, create a PR, merge, deploy, or remove a worktree only when that delivery stage is explicitly approved.

Before delivery:

- confirm the exact base and branch relationship;
- inspect all modified/untracked paths;
- ensure the intended changes are committed;
- rerun the full verification on the exact commit;
- state separately what is committed, pushed, merged, and deployed;
- preserve a rollback path.

### `pd verify` reads SPEC.md literally

- **Any `- [ ]` in `SPEC.md` fails "All requirements addressed" — including non-goals.** The verifier only looks for the unchecked box, so a "Non-goals" list written as checkboxes turns into a false red and blocks delivery. Write non-goals as plain bullets (`- item`) with a one-line note that they are out of scope, and keep checkboxes for requirements and success criteria only.
- **`pd advance` does not run `verify`.** It increments the phase and saves state; the two commands are independent. Run `pd verify` first and treat red as a blocker — advancing a phase with an open requirement leaves the state lying about the work.
- **Delivered-but-unticked is bookkeeping, not scope.** Close `[x]` citing the task/evidence; do not reopen the requirement discussion. If the criterion text no longer matches reality (e.g. "no automatic commit" after a gated merge queue exists), rewrite it to what is true and cite the evidence — never tick it silently and never leave it open.

### Promote a branch to master without checking it out (fast-forward)

When `master` is an ancestor of the delivery branch and is not checked out in any worktree:

```bash
git worktree list                                    # master must not be checked out anywhere
git merge-base --is-ancestor master <branch> && echo ff
git branch -f master <branch>                        # fast-forward move, no merge commit
git push origin <branch> && git push origin master
git fetch origin && for r in HEAD master origin/master origin/<branch>; do git rev-parse --short "$r"; done
```

- With `master` checked out, use `git switch master && git merge --ff-only <branch>` instead; `git branch -f` refuses the checked-out branch.
- **Verify all refs are equal after the push.** A successful push is not proof the refs aligned: print `HEAD`, local `master`, `origin/master` and `origin/<branch>` and require one SHA. A promotion that leaves the branch ahead by one is the same debt again.
- Keep it fast-forward when possible: no merge commit means branch and master share the SHA, and a later revert/rollback is a single pointer move.

## CLI support

The repository includes an optional `pd` CLI for state management:

```bash
pd init <feature-name>
pd status
pd validate --deep
pd checkpoint --note "..."
pd verify
pd advance
pd complete-task "..."
pd list
pd history
pd report
pd diff
```

Use the repository's actual CLI entrypoint and help output. If installing manually, keep the wrapper, `pd.py`, and the `pd_fleet` package together:

```bash
REPO_DIR=/path/to/project-development-skill
mkdir -p ~/.local/bin
ln -sfn "$REPO_DIR/scripts/pd" ~/.local/bin/pd
ln -sfn "$REPO_DIR/scripts/pd.py" ~/.local/bin/pd.py
ln -sfn "$REPO_DIR/scripts/pd_fleet" ~/.local/bin/pd_fleet
chmod +x "$REPO_DIR/scripts/pd" "$REPO_DIR/scripts/pd.py"
pd --help
```

Copying only `pd` and `pd.py` is insufficient because `pd.py` imports `pd_fleet`.

CLI architecture and compatibility notes: `references/cli-tool-architecture.md`.

## Security-sensitive work

For auth, gateways, terminal access, public webhooks, privileged actions, or exposed listeners, run a read-only security reconnaissance wave before approving the SPEC. Keep local tests deterministic and require explicit gates for authentication, ownership, origins, listener binding, authorization, restart, rollback, and log redaction.

Use `references/security-hardening-wave.md` for the matrix and stop conditions.

## External repository adoption

Treat external repositories as adoption decisions, not automatic installers. Audit a pinned revision, license, runtime, security surface, source-of-truth boundaries, and rollback before integration. Keep the first wave isolated, local, read-only or shadow, and credential-free where possible.

For methodology frameworks (spec and planning tools), separate the artifact format from the process philosophy: adopt a schema that makes requirements machine-checkable (requirement + scenario, delta against a living spec) and reject any process rule that contradicts this pipeline's gates. Extract the ideas from skill collections instead of installing the whole pack into the discovery path, where every installed description taxes every prompt. When a context-scoped workspace is used inside PD, keep `.spec/<feature>/` as the only control plane and use stage contracts as bounded read/write instructions; never create a second state machine.

Use `references/external-repo-adoption.md`.

## Product and AI planning

For AI-assisted products, separate canonical user-owned claims/evidence from contextual generated outputs. Do not invent facts. Require provenance, confidence, policy checks, immutable versions, and human approval before external effects.

Use `references/product-ai-pds.md` and `references/vertical-slice-pds.md` when this domain applies.

## Skill source and distribution

When a repository and installed copies disagree, audit every destination, back up before replacement, promote accepted content into a versioned branch, and reinstall from the repository. Verify the complete tree, not only `SKILL.md`.

Hermes can receive the complete directory. Platforms that require a flat command file must either receive bundled references or use a documented platform-specific rendering; links to unavailable `references/` files are not acceptable.

Use `references/skill-source-reconciliation.md` and `references/multi-platform-skill-development.md`.

## Common failure modes

- coding before an approved SPEC and `.spec` state;
- treating a checkpoint as completion;
- continuing dependent work after a failed prerequisite;
- retrying without recording the hypothesis and evidence;
- trusting a worker's test count without rerunning it;
- using `--force` to conceal stale or malformed planning state;
- mixing provider-dependent verification with offline tests;
- merging/rebasing or discarding WIP implicitly;
- claiming a complete installation when references/templates were omitted;
- claiming release readiness from tests alone;
- `PLAN.md` task marks drifting from `STATE.json`, leaving two truths in the same control plane;
- running `pd advance` on the owner's behalf (phase change is an owner decision);
- inventing an orchestration level the method already names;
- treating a gate as crossed because a checkpoint file exists.

## Final checklist

- [ ] `.spec/<feature>/` exists and is valid
- [ ] SPEC approved or explicitly marked draft with authorization
- [ ] PLAN has dependencies, contracts, recovery, and validation commands
- [ ] Failed tasks have evidence and remediation/retry state
- [ ] Dependent tasks are blocked until prerequisites are green
- [ ] Focused and full verification ran on the current workspace
- [ ] Fresh-eyes review completed or explicitly marked blocked
- [ ] VERIFICATION.md distinguishes verified, deferred, and blocked scope
- [ ] Delivery stage explicitly approved
- [ ] STATE.md and STATE.json match observed reality
- [ ] PLAN.md task marks and STATE.json agree (reconcile, do not hand-edit one side)
