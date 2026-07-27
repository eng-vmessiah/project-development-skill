---
name: pd
description: "Bomb-proof development pipeline: brainstorm → spec → plan → code → test → review. Master orchestrator for software projects."
version: 1.1.0
license: MIT
metadata:
  hermes:
    tags: [project-development, pipeline, orchestration, bomb-proof, workflow]
    related_skills: [writing-plans, test-driven-development, requesting-code-review, subagent-driven-development, debugging-discipline, spike]
argument-hint: "What feature or project needs the full pipeline?"
---

# Project Development (PD) — Bomb-Proof Pipeline

**Leading word: bomb-proof** — same as writing-plans. A plan so thorough no implementer has to guess. Phases gate on completion criteria; each phase proves readiness for the next.

## Overview

PD is the **master orchestrator** for software development. It guides you through a complete pipeline from idea to code review, ensuring quality at every step.

**Inspired by:** brainstorming, planning, verification patterns + Context Rot, Wave-Based Execution, STATE.md persistence
**Adapted for:** Hermes Agent + OpenCode + Claude Code

**Multi-platform reference:** See `references/multi-platform-skill-development.md` for sync scripts, attribution patterns, and repo structure.

**CLI tool reference:** See `references/cli-tool-architecture.md` for CLI commands, config, hooks, and testing patterns.

**Cross-boundary TDD reference:** See `references/cross-boundary-tdd.md` for layered event/migration tests, correlation boundary assertions, Vitest hoisting, continuation discipline, sync→async batch telemetry migration, graceful shutdown flush hooks, and call-site telemetry integration patterns.

**Fleet orchestration reference:** See `references/fleet-orchestration.md` for role contracts, wave gates, safe parallelism, prompt refinement, and the implementation sequence for supervised subagent fleets. For post-implementation grill, real-CLI probes, checkpoint round-trip, and honest PASS/PARTIAL closeout, see `references/fleet-orchestration-closeout.md`. For canonical identity, strict reconciliation envelopes, hostile-input probes, and cross-module hardening residuals, see `references/fleet-hardening-contracts.md`.

## 🚨 BLOCKER — DO NOT CODE FIRST

**Before writing ANY code, you MUST complete:**
1. Brainstorming (understand the problem)
2. Planning (define the approach)
3. Create `.spec/` structure

**There are NO exceptions.** Even "simple" tasks need a brief design.

## CLI Commands

The PD CLI manages state and validates progress. Use it to track your workflow:

```bash
# Initialize a new feature
pd init <feature-name>

# Check current status
pd status

# Validate progress
pd validate
pd validate --deep    # Content validation (checks SPEC/PLAN/VERIFICATION)

# Create checkpoint
pd checkpoint --note "Completed Phase 2"

# Verify before completing
pd verify

# Advance to next phase
pd advance
pd advance --dry-run   # Preview without changing state
pd advance --force     # Skip validation

# Mark task as complete
pd complete-task "Implemented user model"

# List all features
pd list

# Delete/archive a feature
pd delete <feature-name> --archive

# Show checkpoint timeline
pd history

# Generate progress report
pd report

# Show changes since last checkpoint
pd diff

# Generate shell completions
pd completion bash   # or zsh, fish
```

### Global Flags

```bash
-f, --feature    # Target specific feature (default: most recent)
--json           # JSON output for all commands
--dry-run        # Preview without changing state
--force          # Skip confirmations and validation
--no-color       # Disable colored output
```

**State is persisted in `.spec/<feature>/STATE.json` + `STATE.md`** — the CLI reads and updates both files.

### Installing the PD CLI

The PD CLI lives in the `project-development-skill` repo. Install it with:

```bash
# From the repo
REPO_DIR=/path/to/project-development-skill
ln -sf "$REPO_DIR/scripts/pd" ~/.local/bin/pd
cp "$REPO_DIR/scripts/pd.py" ~/.local/bin/pd.py
chmod +x ~/.local/bin/pd ~/.local/bin/pd.py

# Verify
pd init --help
pd status --json
```

The bash wrapper resolves `pd.py` from the same directory the symlink points to, so both files must share a directory. The Python script has no external dependencies beyond the standard library.

## The Prime Directive

```
NO SPECIFICATION + PLAN, NO CODE
```

If you haven't completed brainstorming and planning, you cannot write code.

## When NOT to Use (Skip the pipeline if:)

Task fits in one short prompt, completed in one turn without clarification. Variable rename, typo fix, missing import, simple bug with obvious cause.

**Rule of thumb:** Needs research? Files you haven't read? Decisions unsettled? Use the pipeline. Otherwise, skip.

## When to Use

- Starting a new project or feature
- User says: "quero criar", "vamos implementar", "nova feature"
- Coding task needing planning before implementation
- Multi-file features, cross-cutting refactors, work spanning hours/sessions
- Evaluating an external repository or framework for possible future adoption

## Domain Action Contract Migrations

When adapting an external agent-native action pattern into an existing API, use a compatibility-first, test-first migration rather than importing the framework wholesale:

1. Audit legacy and target flows separately. Keep prompt-driven legacy routes out of the first action boundary when they mix model calls, parsing, persistence, chat, and status mutation.
2. Create and verify a registered Git worktree from the intended implementation branch before reading/editing source.
3. Select the smallest safe domain action, preferably read-only validation before dispatch.
4. Write RED tests for a versioned action envelope, stable error codes, actor/source/request context, and durable audit evidence.
5. Preserve legacy response shapes under a compatibility endpoint while introducing the new action endpoint. Update legacy tests to call the compatibility route explicitly.
6. Use an additive durable audit table/event seam; never report an audit as recorded from a best-effort logger without a successful write.
7. Verify RED, focused legacy regression tests, then the full suite; record exact counts and classify unrelated warnings/failures separately.
8. Update `STATE`, `CHECKPOINT`, and verification artifacts with exact worktrees, commits, gates, and deferred surfaces before publishing.

See `references/domain-action-contract-migrations.md` for the reusable checklist and envelope example.

### Action-contract persistence and continuation gates

For a domain action that crosses backend, frontend, audit, and future agent surfaces, keep the implementation incremental and compatibility-first:

1. Separate the new versioned action route from a legacy route whose response shape is already consumed. Migrate tests and consumers explicitly; do not silently change the legacy contract.
2. Add durable audit writes before exposing audit reads. The read API must be owner-scoped, resource/action-filterable, paginated with hard bounds, and redact owner/secrets.
3. Add idempotency before any future dispatch surface: same owner/action/resource/key replays the same bounded response and audit ID; key reuse for another resource returns a stable conflict.
4. When the local SQLite database may predate the feature, add an additive schema migration and test it against an existing database shape. Fresh-database tests alone are insufficient.
5. Make test fixtures order-independent. Shared SQLite state requires unique resource-derived keys or an isolated database; fixed idempotency keys create false failures after prior runs.
6. After each gate, run the focused slice and the full suite, then update `STATE`, `CHECKPOINT`, and `VERIFICATION` with exact counts and commit IDs. A checkpoint is not a stopping point when the user said “continue/seguir”: start the next unblocked gate in the same turn.
7. For write-action migrations, introduce a parallel versioned route (`/api/actions/<action>`) before changing the legacy route. Reuse the legacy domain validators and persistence only after validation succeeds; add `dispatch_started: false` explicitly until dispatch is separately gated.
8. Treat `create` and `update` actions as separate red-green slices. Test first-write status, replay status, stable audit identity, cross-resource idempotency conflict, and invalid mutation non-persistence. Keep the old endpoint tests pointed at the old response shape.
9. Reconcile generic action names with the concrete host route before documenting completion (`validate_mission_plan`, not a stale `validate_mission`). Keep PDS names, frontend types, route names, and checkpoint evidence aligned.

The reusable action-contract details remain in `references/domain-action-contract-migrations.md`; this subsection records the persistence, migration, fixture, write-action, naming, and continuation pitfalls found during implementation.

## External Adoption PDS

When an external repository is promising but adoption is deferred, create a **documentation-only PDS branch/worktree** instead of installing it into the active runtime or creating speculative code. Preserve existing WIP and keep the target branch clean.

Required artifacts under `.spec/<feature>/`:

```text
README.md         # document map and guardrail
SPEC.md           # problem, requirements, non-goals, success criteria
RESEARCH.md       # audited revision, comparison, evidence and caveats
CONTEXT.md        # host architecture, source-of-truth and integration boundaries
PLAN.md           # staged spike/adoption waves with gates and rollback
STATE.md          # human-readable persistent state
STATE.json        # machine-readable persistent state
CHECKPOINT.md     # exact resumption point and delivery boundary
VERIFICATION.md   # what was verified vs explicitly not verified
DECISIONS.md      # accepted and open architectural decisions
```

The PDS must explicitly distinguish **architectural relevance** from **adoption readiness**, classify the candidate as replacement/index/sidecar/adapter, and state whether it creates a competing source of truth. For memory/brain systems, map the candidate against the existing human-readable source, machine memory, provenance, stale-fact handling, retention/deletion, privacy/data egress and authority precedence.

Recommended sequence:

1. Audit the pinned external revision in an isolated clone; do not trust README claims as verification.
2. Validate setup in the isolated clone when practical, recording runtime/version limitations precisely.
3. Create a separate branch/worktree from a clean base; never absorb unrelated WIP.
4. Write the complete PDS before implementation: sanitized spike, baseline, security, privacy, rollback and adoption gates.
5. Keep the first future wave read-only/shadow/local where possible; defer remote exposure and active-runtime configuration.
6. Validate JSON/diff hygiene and secret scans, then commit/push the documentation branch when delivery is requested.

Do not execute an external agent-driven installer, import a full vault, add a second authoritative memory, restart services, or modify active Hermes configuration merely because a repository offers a convenient quickstart.

## Context Rot

**Problem:** As the context window fills, quality degrades silently. The model starts contradicting earlier decisions, code style drifts, plans ignore requirements.

**Why it happens:** Transformer attention weights relevance across a finite window. As noise accumulates, signal-to-noise degrades.

**Symptoms:**
- Model contradicts earlier decisions
- Code style drifts from conventions
- Plans ignore clearly stated requirements
- Hallucinated file names or function signatures

**Solution:** Fresh-context subagents for heavy work.

### Context Rules

| Task Size | Context Strategy |
|-----------|------------------|
| <5 tasks | Sequential in main context |
| 5-10 tasks | Parallel subagents, fresh context each |
| >10 tasks | Wave-based execution (see below) |
| Cross-session | STATE.md persists context |

### Atomic Task Execution (Ralph Pattern)

> **"One goal, one context window."** — Jeff Huntley

For multi-step features, apply the **atomic task execution** pattern extracted from the `ralph-loop-skills` methodology. The insight: **compaction is the devil**. Never let a single context window extend across multiple implementation tasks.

**The Loop:**

```
while tasks_remain:
    1. Read PLAN.md → find first unchecked `- [ ]` task
    2. Spawn FRESH subagent (zero compaction)
    3. Subagent: read spec → implement → test → report
    4. If success: mark `- [x]` in PLAN.md, commit
    5. If failure: log error, continue to next task (don't block the loop)
    6. Repeat
```

**Key rules:**
- **One task per context window** — subagent never sees the previous task's code or reasoning
- **Fresh subagent each iteration** — avoids context pollution
- **PLAN.md as state machine** — checkboxes are the source of truth, not STATE.md
- **Commit per task** — clean git history, rollback scope is one task
- **Outer loop is cheap** — the cost of spawning a new subagent is negligible vs the cost of degraded output from compaction

**When to use:** Features with 3+ implementation tasks. For 1-2 simple tasks, sequential in the main context is fine.

**Pitfalls:**
- Subagent timeout leaves dirty state. After timeout: check which files changed, handle remaining work manually.
- Don't loop ASK for continuation between tasks. After marking `- [x]`, immediately dispatch the next subagent.
- If a subagent fails 3 consecutive times, stop the loop and report the error to the user.

### The Orchestrator Principle

The main session (orchestrator) should:
- **Never touch source files directly** — delegate to subagents
- **Stay lean** — only spawn agents, collect results, update state
- **Grow slowly** — context window should be predictable

Each subagent should:
- **Start fresh** — clean context window
- **Receive exactly what it needs** — project summary, phase context, specific task
- **Terminate when done** — report results back to orchestrator

## Wave-Based Execution

For complex features with >10 tasks, organize into **waves**:

### Wave Structure

```
Wave 1 (Foundation):
├── Task 1: Setup infrastructure
├── Task 2: Create models
└── Task 3: Define interfaces

Wave 2 (Core - parallel):
├── Task 4: Backend endpoint A (depends: Wave 1)
├── Task 5: Backend endpoint B (depends: Wave 1)
└── Task 6: Frontend component (depends: Wave 1)

Wave 3 (Integration - parallel):
├── Task 7: Integration tests (depends: Wave 2)
└── Task 8: API tests (depends: Wave 2)

Wave 4 (Verification):
└── Task 9: Full verification (depends: Wave 3)
```

### Wave Rules

1. **Tasks in same wave** — must be independent (non-overlapping file paths)
2. **Waves execute sequentially** — Wave 2 starts after Wave 1 completes
3. **Parallel within wave** — use `delegate_task` for tasks in same wave
4. **Fresh context each** — each subagent gets clean context

### Fleet Coordination Upgrade

For goals that need a fleet rather than a single worker, treat PD as an executable coordination protocol, not merely a list of phases. Refine the goal before planning, compile a task DAG with explicit contracts, grill the plan, then release only dependency-ready tasks to bounded workers. The orchestrator owns state, blockers, retries, and evidence; it should not opportunistically implement source changes assigned to workers.

Every fleet task must declare its role, dependencies, allowed and forbidden paths, inputs, outputs, acceptance criteria, validation commands, and blocked conditions. Parallel execution is allowed only when dependencies are complete, decisions are closed, inputs exist, and write ownership cannot conflict. Use separate worktrees or explicit path ownership for parallel writers.

Use explicit gates for intake, discovery/spec, plan grill, implementation, integration, review/grill, smoke/evidence, and closeout. Worker reports are leads, not proof: independently verify critical files and rerun important commands before changing task state to completed.

Run prompt refinement twice: first to turn a vague goal into an executable plan; last to turn the plan, grill findings, decisions, and residual risks into a reusable next-session prompt. Keep the prompt as a file artifact. See `references/fleet-orchestration.md` for the role table, task contract, gate sequence, anti-patterns, and staged adoption order.

### Fleet closeout is a runtime gate, not a test-count gate

After the first green implementation wave, dispatch independent spec, quality/security, and adversarial-grill reviews. Treat subagent reports as leads and independently verify files, test paths, counts, and the real CLI entrypoint. Confirm that runtime authorization consumes full contracts (for example, a policy-validated `GateResult`, never `status: passed` alone), that retry/inputs/readiness semantics agree, and that generated checkpoints load through the canonical parser. Exercise normal, dry-run, resume, malformed, missing-plan, and blocked-gate CLI paths in a temporary working directory. Turn confirmed blockers/high findings into explicit remediation waves, rerun fresh full verification, and write `VERIFICATION.md` with PASS/PARTIAL/BLOCKED per requirement. Do not report a global PASS while human/provider/command-execution or deployment-dependent scope remains unverified. Detailed probes and caveats live in `references/fleet-orchestration-closeout.md`.

### Multi-wave merge-readiness gate

For a long-running plan executed by multiple subagents, separate **implementation complete**, **verification complete**, and **merge-ready**. A green suite does not make a dirty worktree mergeable.

Before saying “ready to merge with main”:

1. Run `git status --short --branch`, `git branch -vv`, and `git log --graph --decorate --all`; identify the exact base and whether the branch is ahead/behind.
2. Inventory every modified and untracked path. Do not assume the user changed only the original entrypoint: subagents may have created modules, tests, docs, fixtures, and artifacts across the plan.
3. Independently verify each subagent claim (file existence, scoped ownership, exact test command, and output). Reports are leads, not evidence.
4. Keep the worktree dirty until the scope is reviewed; never merge, rebase, stash, reset, or discard it implicitly. Group changes into logical commits only after the user approves delivery scope.
5. Rebase/merge from the current base only after the feature work is committed or deliberately staged in an isolated checkpoint; never perform integration on an uncommitted worktree.
6. Re-run the full suite, static checks, path/ownership checker, and changed-file review on the exact commit intended for merge.
7. Distinguish an experimental/local merge from an operational release. Explicitly record deferred sandbox, provider, dispatch, deployment, and human-approval gates.

If the user asks “why is the worktree dirty?” answer with the path inventory and explain whether the dirt is intentional subagent WIP, generated artifacts, or accidental scope creep. See `references/multi-wave-closeout.md` for the reusable checklist.

## Multi-Agent Orchestration Patterns

### Agent Roles

| Role | Purpose | When to Use |
|------|---------|-------------|
| **Orchestrator** | Coordinates agents, manages state | Main session |
| **Worker** | Executes specific tasks | Parallel execution |
| **Reviewer** | Validates work | Quality checks |
| **Specialist** | Domain expertise | Complex problems |

### Agent Collaboration Patterns

#### Pattern 1: Supervisor-Worker
```
Orchestrator
├── Worker A (task 1)
├── Worker B (task 2)
└── Worker C (task 3)
```

**Use when:** Tasks are independent, can run in parallel.

```python
# Supervisor-worker pattern
delegate_task(
    tasks=[
        {"goal": "Implement auth module", "toolsets": ["terminal", "file"]},
        {"goal": "Implement API routes", "toolsets": ["terminal", "file"]},
        {"goal": "Write tests", "toolsets": ["terminal", "file"]}
    ]
)
```

#### Pattern 2: Pipeline
```
Agent A ──► Agent B ──► Agent C ──► Result
```

**Use when:** Output of one agent feeds into next.

```python
# Pipeline pattern
result_a = delegate_task("Research requirements")
result_b = delegate_task(f"Design based on: {result_a}")
result_c = delegate_task(f"Implement based on: {result_b}")
```

#### Pattern 3: Review Loop
```
Worker ──► Reviewer ──► Fix ──► Reviewer ──► Done
```

**Use when:** Quality is critical, need validation.

```python
# Review loop pattern
work = delegate_task("Implement feature")
review = delegate_task(f"Review this code:\n{work}")

if review.contains_issues:
    fixes = delegate_task(f"Fix issues:\n{review.issues}")
    final_review = delegate_task(f"Verify fixes:\n{fixes}")
```

#### Pattern 4: Swarm (Specialist)
```
Orchestrator
├── Python Expert
├── TypeScript Expert
└── DevOps Expert
```

**Use when:** Different domains need specialized knowledge.

```python
# Swarm pattern
delegate_task(
    tasks=[
        {"goal": "Optimize Python backend", "toolsets": ["terminal", "file"]},
        {"goal": "Refactor React components", "toolsets": ["terminal", "file"]},
        {"goal": "Setup CI/CD pipeline", "toolsets": ["terminal", "file"]}
    ],
    role="orchestrator"
)
```

### Agent Policies

Control what agents can do:

```yaml
# Agent policy examples
policies:
  # Safety
  approve_shell:
    type: function
    handler: ask_before_shell_commands
  
  # Cost control
  budget:
    type: function
    handler: max_cost_usd
    params:
      limit: 5.00
  
  # Tool limits
  tool_calls:
    type: function
    handler: max_tool_calls
    params:
      limit: 50
```

### Agent Communication

#### Via Context Passing
```python
# Pass context between agents
agent_a_result = delegate_task("Analyze codebase")
agent_b_result = delegate_task(
    f"Based on this analysis:\n{agent_a_result}\n\nImplement improvements"
)
```

#### Via Shared State Files
```python
# Agents read/write to shared files
delegate_task("Write analysis to /tmp/analysis.md")
delegate_task("Read /tmp/analysis.md and implement recommendations")
```

### Agent Quality Gates

Before claiming completion, agents must verify:

```python
# Quality gate checklist
quality_checklist = """
- [ ] Code compiles/runs
- [ ] Tests pass
- [ ] No lint errors
- [ ] Follows style guide
- [ ] Meets requirements
"""
```

### Anti-Patterns in Multi-Agent

| Pattern | Problem |
|---------|---------|
| Too many agents | Coordination overhead |
| No clear roles | Confusion, duplication |
| Blocking dependencies | Sequential bottleneck |
| No quality gates | Low-quality output |
| Ignoring cost | Budget overruns |

### Parallel Execution with delegate_task

```python
# Example: Wave 2 (Backend + Frontend in parallel)
delegate_task(
    tasks=[
        {
            "goal": "Implement backend endpoint A",
            "context": "Load clean-code skill. Follow .spec/01-feature/backend/task-04.md. Fresh context: read SPEC.md, PLAN.md, models from Wave 1.",
            "toolsets": ["terminal", "file"]
        },
        {
            "goal": "Implement backend endpoint B", 
            "context": "Load clean-code skill. Follow .spec/01-feature/backend/task-05.md. Fresh context: read SPEC.md, PLAN.md, models from Wave 1.",
            "toolsets": ["terminal", "file"]
        },
        {
            "goal": "Implement frontend component",
            "context": "Load clean-code skill. Follow .spec/01-feature/frontend/task-06.md. Fresh context: read SPEC.md, PLAN.md, interfaces from Wave 1.",
            "toolsets": ["terminal", "file"]
        }
    ]
)
```

## Rationalization Detection

These thoughts mean STOP — you're rationalizing:

| Thought | Reality |
|---------|---------|
| "This is just a simple question" | Questions are tasks. Check for skills. |
| "I need more context first" | Skill check comes BEFORE clarifying questions. |
| "Let me explore the codebase first" | Skills tell you HOW to explore. Check first. |
| "I can check git/files quickly" | Files lack conversation context. Check for skills. |
| "Let me gather information first" | Skills tell you HOW to gather information. |
| "This doesn't need a formal skill" | If a skill exists, use it. |
| "I remember this skill" | Skills evolve. Read current version. |
| "This doesn't count as a task" | Action = task. Check for skills. |
| "The skill is overkill" | Simple things become complex. Use it. |
| "I'll just do this one thing first" | Check BEFORE doing anything. |
| "This feels productive" | Undisciplined action wastes time. Skills prevent this. |
| "I know what that means" | Knowing the concept ≠ using the skill. Invoke it. |

## Skill Priority

When multiple skills could apply, use this order:

1. **Process skills first** (pd, brainstorming, debugging) — determine HOW to approach
2. **Implementation skills second** (clean-code, ddd-development) — guide execution

Examples:
- "Let's build X" → PD first, then clean-code + ddd-development
- "Fix this bug" → systematic-debugging first, then pd if needed
- "Write tests" → test-driven-development first

## Skill Types

| Type | Examples | Behavior |
|------|----------|----------|
| **Rigid** | TDD, debugging, verification | Follow exactly. Don't adapt away discipline. |
| **Flexible** | clean-code, ddd-development | Adapt principles to context. |

The skill itself tells you which.

---

## Phase 0: Worktree (Optional but Recommended)

**Goal:** Isolate feature work in a git worktree to avoid conflicts.

### When to Use

- Feature will take >30 min
- Multiple features in parallel
- Risky changes that might break main

### Worktree Setup

```bash
# Create worktree for feature
git worktree add ../feature-name feature/01-user-auth

# Work in isolated directory
cd ../feature-name

# When done, merge and cleanup
git checkout main
git merge feature/01-user-auth
git worktree remove ../feature-name
```

### Worktree Rules

1. **One worktree per feature** — don't mix features
2. **Branch naming:** `feature/XX-name`
3. **Commit frequently** — keep worktree up to date
4. **Merge when done** — cleanup worktrees after merge

---

## Pipeline Phases

```
┌─────────────────────────────────────────────────────────────┐
│  PHASE 0: WORKTREE (opcional)                               │
│  Output: git worktree isolado para a feature                │
├─────────────────────────────────────────────────────────────┤
│  PHASE 1: BRAINSTORMING                                     │
│  Output: .spec/XX-feature/SPEC.md                           │
├─────────────────────────────────────────────────────────────┤
│  PHASE 2: PLANNING                                          │
│  Output: .spec/XX-feature/PLAN.md                           │
├─────────────────────────────────────────────────────────────┤
│  PHASE 3: STRUCTURE                                         │
│  Output: .spec/XX-feature/{backend,frontend,tests}/         │
├─────────────────────────────────────────────────────────────┤
│  PHASE 4: CODING (paralelo ou sequencial)                   │
│  Output: Implementation following PLAN.md                   │
├─────────────────────────────────────────────────────────────┤
│  PHASE 5: TESTING                                           │
│  Output: Tests in .spec/XX-feature/tests/                   │
├─────────────────────────────────────────────────────────────┤
│  PHASE 6: REVIEW                                            │
│  Output: .spec/XX-feature/CHECKPOINT.md                     │
├─────────────────────────────────────────────────────────────┤
│  PHASE 7: MERGE (cleanup do worktree)                       │
│  Output: Feature merged, worktree removido                  │
└─────────────────────────────────────────────────────────────┘
```

---

## Phase 1: Brainstorming

**Goal:** Understand the problem, explore approaches, get user approval.

### Checklist

1. **Explore project context** — check existing code, docs, recent commits
2. **Ask clarifying questions** — one at a time, understand purpose/constraints
3. **Propose 2-3 approaches** — with trade-offs and recommendation
4. **Present design** — get user approval
5. **Write SPEC.md** — save to `.spec/XX-feature/SPEC.md`
6. **User reviews spec** — confirm before proceeding

### SPEC.md Template

```markdown
# [Feature Name] — Specification

**Date:** YYYY-MM-DD
**Status:** `draft` | `approved` | `implemented`

## Problem Statement
[What problem does this solve?]

## Requirements
- [ ] Requirement 1
- [ ] Requirement 2

## Proposed Approaches

### Approach A: [Name]
- Pros: ...
- Cons: ...

### Approach B: [Name]
- Pros: ...
- Cons: ...

## Recommended Approach
[Which one and why]

## Success Criteria
- [ ] Criterion 1
- [ ] Criterion 2

## Constraints
- Technical constraints
- Business constraints
- Timeline constraints
```

---

## Phase 2: Planning

**Goal:** Break the design into bite-sized tasks (2-5 min each).

### Checklist

1. **Map file structure** — which files to create/modify
2. **Define tasks** — each task is one action (2-5 min)
3. **Order tasks** — dependencies, TDD order
4. **Write PLAN.md** — save to `.spec/XX-feature/PLAN.md`

### PLAN.md Template

```markdown
# [Feature Name] — Implementation Plan

**Goal:** [One sentence]
**Architecture:** [2-3 sentences]
**Tech Stack:** [Key technologies]

## File Structure

```
feature/
├── backend/
│   ├── models.py
│   └── endpoints.py
├── frontend/
│   └── components/
└── tests/
    ├── unit/
    └── integration/
```

## Tasks

### Backend
- [ ] 1. Create User model (models.py)
- [ ] 2. Write failing test for create_user
- [ ] 3. Implement create_user endpoint
- [ ] 4. Write failing test for validate_email
- [ ] 5. Implement email validation

### Frontend
- [ ] 6. Create LoginForm component
- [ ] 7. Write failing test for form validation
- [ ] 8. Implement form validation

### Tests
- [ ] 9. Write unit tests for model
- [ ] 10. Write integration tests for API
- [ ] 11. Ensure all tests pass

## Estimated Time
- Backend: ~30 min
- Frontend: ~20 min
- Tests: ~15 min
- Total: ~65 min
```

---

## Phase 3: Structure

**Goal:** Create the `.spec/` directory structure with STATE.md as the spine.

### STATE.md — Project Memory

STATE.md is the **navigation layer** that carries context across sessions. It records exactly where the project is in the pipeline.

**Every workflow reads STATE.md first, writes back when done.**

> **Note:** The CLI maintains a dual backend — STATE.json (structured, used by the CLI for reliable parsing) alongside STATE.md (human-readable). On first load of existing features, auto-migrates from STATE.md → STATE.json.

### Directory Layout

```
.spec/
├── README.md                              # Project overview
├── STATE.md                               # Project memory (spine)
├── .templates/
│   ├── TASK.md
│   ├── CHECKPOINT.md
│   └── STATUS.md
│
├── 01-feature-name/
│   ├── SPEC.md                            # From Phase 1 (Brainstorm)
│   ├── PLAN.md                            # From Phase 2 (Planning)
│   ├── CONTEXT.md                         # Implementation decisions
│   ├── RESEARCH.md                        # Domain research (if needed)
│   ├── VERIFICATION.md                    # Verification results
│   │
│   ├── backend/
│   │   ├── README.md                      # Backend index
│   │   ├── 01-create-model.md
│   │   ├── 02-create-endpoint.md
│   │   └── STATUS.md
│   │
│   ├── frontend/
│   │   ├── README.md
│   │   ├── 01-login-form.md
│   │   └── STATUS.md
│   │
│   ├── tests/
│   │   ├── README.md
│   │   ├── 01-unit-tests.md
│   │   ├── 02-integration-tests.md
│   │   └── STATUS.md
│   │
│   └── CHECKPOINT.md
```

### STATE.md Template

```markdown
# Project State

**Last Updated:** YYYY-MM-DD HH:MM
**Current Phase:** [phase number/name]
**Status:** `planning` | `executing` | `verifying` | `complete`

## Current Milestone
[Milestone name and goal]

## Active Phase
- **Phase:** [number]
- **Goal:** [one sentence]
- **Status:** [current status]

## Progress
| Phase | Status | Plans | Tasks Done |
|-------|--------|-------|------------|
| 1. Feature A | complete | 3/3 | 12/12 |
| 2. Feature B | executing | 2/4 | 8/15 |
| 3. Feature C | pending | 0/0 | 0/0 |

## Decisions
- [Decision 1]
- [Decision 2]

## Blockers
- [Blocker 1]

## Metrics
- Total tasks: X
- Completed: Y
- Coverage: Z%
```

### CONTEXT.md Template

```markdown
# Implementation Context

**Phase:** [number]
**Date:** YYYY-MM-DD

## Decisions
- **Library:** [choice] — because [reason]
- **Pattern:** [choice] — because [reason]
- **Error handling:** [strategy]

## Constraints
- Must use [technology]
- Cannot modify [file]
- Performance target: [metric]

## Edge Cases
- [Edge case 1]: [how to handle]
- [Edge case 2]: [how to handle]

## References
- [Link to docs]
- [Link to examples]
```

### Task File Format

```markdown
# [Task Name]

**Status:** `pending` | `in_progress` | `done` | `blocked`
**Depends:** #task-anterior
**Estimated:** 2-5 min

## Objective
[What this task does]

## Acceptance Criteria
- [ ] Criterion 1
- [ ] Criterion 2

## Implementation Notes
[Details about how to implement]
```

---

## Phase 4: Coding (Executing Plans)

**Goal:** Implement tasks following the PLAN.md. Can run sequentially or in parallel.

### The Process

#### Step 1: Load and Review Plan
1. Read PLAN.md file
2. Review critically — identify any questions or concerns
3. If concerns: Raise them before starting
4. If no concerns: Create todo list and proceed

#### Step 2: Execute Tasks
For each task:
1. Mark as `in_progress`
2. Follow each step exactly (plan has bite-sized steps)
3. Run verifications as specified
4. Mark as `done`

#### Step 3: Complete Development
After all tasks complete and verified:
- Run Phase 6 (Review & Verification)
- Create CHECKPOINT.md

### When to Stop and Ask for Help

**STOP executing immediately when:**
- Hit a blocker (missing dependency, test fails, instruction unclear)
- Plan has critical gaps preventing starting
- You don't understand an instruction
- Verification fails repeatedly

**Ask for clarification rather than guessing.**

### When to Revisit Earlier Steps

**Return to Planning when:**
- Partner updates the plan based on your feedback
- Fundamental approach needs rethinking

**Don't force through blockers** — stop and ask.

### Sequential vs Parallel

| Scenario | Mode | How |
|----------|------|-----|
| Simple feature (<5 tasks) | Sequential | One task at a time |
| Complex feature (>5 tasks) | Parallel | delegate_task for independent tasks |
| Backend + Frontend independent | Parallel | Split into subagents |
| TDD (test first) | Sequential | Write test → implement → repeat |

### Parallel Execution with delegate_task

```python
# Example: Backend + Frontend in parallel
delegate_task(
    tasks=[
        {
            "goal": "Implement backend endpoints following PLAN.md backend section",
            "context": "Load clean-code skill. Follow .spec/01-feature/backend/ tasks.",
            "toolsets": ["terminal", "file"]
        },
        {
            "goal": "Implement frontend components following PLAN.md frontend section", 
            "context": "Load clean-code skill. Follow .spec/01-feature/frontend/ tasks.",
            "toolsets": ["terminal", "file"]
        }
    ]
)
```

### Parallel Rules

1. **Independent tasks only** — don't parallelize tasks with dependencies
2. **Separate file paths** — backend/ and frontend/ can be parallel
3. **Tests always last** — after implementation is complete
4. **Review is sequential** — one review at a time

### Coding Checklist

- [ ] Load `clean-code` skill
- [ ] Load `ddd-development` skill (if modeling domain)
- [ ] Review PLAN.md critically before starting
- [ ] Follow task order from PLAN.md
- [ ] Update task status in `.spec/`
- [ ] Run verifications after each task
- [ ] Commit after each task or logical unit
- [ ] Stop and ask if blocked (don't guess)

---

## Phase 5: Testing & Debugging

**Goal:** Write tests using TDD, debug systematically when failures occur.

### TDD Rules

1. **Load `test-driven-development` skill** — follow RED-GREEN-REFACTOR
2. **Write tests in `.spec/XX-feature/tests/`**
3. **Track test status**

### Bug-Driven Coverage (from ai-regression-testing)

**Don't aim for 100% coverage. Test where bugs were found:**

```
Bug in /api/users/profile  → Write test for profile API
Bug in /api/pets           → Write test for pets API
No bug in /api/bookings    → Don't write test (yet)
```

AI repeats the same mistake category. Once tested, that regression **cannot happen again**.

### Response Shape Contracts (from ai-regression-testing)

Define required fields contract per endpoint. Test ALL return the fields:

```typescript
// Contract: every GET /users/me MUST return these fields
const REQUIRED_FIELDS = ['id', 'name', 'email', 'avatarUrl']

describe('GET /users/me', () => {
  it('returns all required fields', async () => {
    const res = await api.get('/users/me')
    for (const field of REQUIRED_FIELDS) {
      expect(res.body).toHaveProperty(field)
    }
  })
})
```

### Data Query Completeness (from ai-regression-testing)

Regression: AI added field to response schema but forgot to include it in the data query:

```typescript
it('response includes newly added field', async () => {
  const res = await api.get('/items')
  const items = res.body

  for (const item of items) {
    expect(item).toHaveProperty('newField')  // ← often forgotten in query
  }
})
```

### Optimistic Update Rollback (from ai-regression-testing)

```typescript
// regression: optimistic update without rollback
it('restores previous state on API failure', async () => {
  const previousState = getState()

  await triggerAction('invalid-id')  // fails

  // State should be restored to previous
  expect(getState()).toEqual(previousState)
})
```

### Key Anti-Patterns to Scan For (from ai-regression-testing)

1. **State mutation before API response** — `setState(data)` then `await api.post(...)`. If API fails, state is wrong.
2. **as any / @ts-ignore in new code** — check that they're justified, not laziness.
3. **SELECT * changed** — if schema changed, did query update too?
4. **Error handling gaps** — `.catch(() => {})` or missing rollback paths.

### Systematic Debugging

**Core principle:** ALWAYS find root cause before attempting fixes. Symptom fixes are failure.

```
NO FIXES WITHOUT ROOT CAUSE INVESTIGATION FIRST
```

#### Phase 1: Root Cause Investigation

**BEFORE attempting ANY fix:**

1. **Read Error Messages Carefully**
   - Don't skip past errors or warnings
   - They often contain the exact solution
   - Read stack traces completely
   - Note line numbers, file paths, error codes

2. **Reproduce Consistently**
   - Can you trigger it reliably?
   - What are the exact steps?
   - Does it happen every time?
   - If not reproducible → gather more data, don't guess

3. **Check Recent Changes**
   - What changed that could cause this?
   - Git diff, recent commits
   - New dependencies, config changes
   - Environmental differences

4. **Gather Evidence in Multi-Component Systems**
   ```
   For EACH component boundary:
     - Log what data enters component
     - Log what data exits component
     - Verify environment/config propagation
     - Check state at each layer

   Run once to gather evidence showing WHERE it breaks
   THEN analyze evidence to identify failing component
   THEN investigate that specific component
   ```

#### Phase 2: Hypothesis Formation

Based on evidence from Phase 1:
1. List possible root causes
2. Rank by likelihood
3. Design test for most likely cause

#### Phase 3: Fix Implementation

1. Implement minimal fix for root cause
2. Don't refactor during debugging
3. Keep changes focused

#### Phase 4: Verification

1. Run original failing test — must pass
2. Run full test suite — no regressions
3. Commit fix

### When to Use Debugging

**Use for ANY technical issue:**
- Test failures
- Bugs in production
- Unexpected behavior
- Performance problems
- Build failures
- Integration issues

**Use this ESPECIALLY when:**
- Under time pressure (emergencies make guessing tempting)
- "Just one quick fix" seems obvious
- You've already tried multiple fixes
- Previous fix didn't work
- You don't fully understand the issue

**Don't skip when:**
- Issue seems simple (simple bugs have root causes too)
- You're in a hurry (rushing guarantees rework)
- Manager wants it fixed NOW (systematic is faster than thrashing)

### Testing Checklist

- [ ] Load `test-driven-development` skill
- [ ] Write unit tests
- [ ] Write integration tests
- [ ] Define Response Shape Contracts
- [ ] Test Data Query Completeness
- [ ] Test Optimistic Update Rollback
- [ ] Scan for anti-patterns
- [ ] All tests passing
- [ ] If tests fail: Load `systematic-debugging` skill
- [ ] Follow Root Cause Investigation before fixing

---

## Phase 6: Review & Validation

**Goal:** Verify what was BUILT matches what was PLANNED and DECIDED.

### Evidence-Based Completion

```
NO COMPLETION CLAIMS WITHOUT FRESH EVIDENCE
```

If you haven't run the verification command in this message, you cannot claim it passes.

### Validation ≠ Testing

**Testing** checks: "Does the code work?"
**Validation** checks: "Did we build the right thing?"

Validation checks:
1. **Requirement coverage** — were all REQ-IDs addressed?
2. **Decision coverage** — were CONTEXT.md decisions implemented?
3. **Phase goal alignment** — does built = planned = decided?

### Quality Gate

```
BEFORE claiming any status or expressing satisfaction:

1. IDENTIFY: What command proves this claim?
2. RUN: Execute the FULL command (fresh, complete)
3. READ: Full output, check exit code, count failures
4. VERIFY: Does output confirm the claim?
   - If NO: State actual status with evidence
   - If YES: State claim WITH evidence
5. ONLY THEN: Make the claim

Skip any step = lying, not verifying
```

### Verification Checklist

- [ ] **Requirement coverage** — read SPEC.md, verify each requirement
- [ ] **Decision coverage** — read CONTEXT.md, verify each decision
- [ ] **Tests passing** — run test command, see output
- [ ] **Linter clean** — run linter, see output
- [ ] **Build succeeds** — run build, see output
- [ ] **No regressions** — git diff, verify changes
- [ ] **VERIFICATION.md created** — document findings

### Verification Template

```markdown
# Verification Report

**Phase:** [number]
**Date:** YYYY-MM-DD
**Status:** `pass` | `fail` | `partial`

## Requirement Coverage
| REQ-ID | Description | Status | Evidence |
|--------|-------------|--------|----------|
| REQ-001 | User can login | ✅ | test output |
| REQ-002 | Password validation | ✅ | test output |
| REQ-003 | OAuth support | ❌ | not implemented |

## Decision Coverage
| Decision | Implemented | Evidence |
|----------|-------------|----------|
| Use bcrypt for hashing | ✅ | lib/auth.py:45 |
| JWT expiration: 24h | ✅ | config.py:12 |

## Test Results
```bash
[command output here]
```

## Linter Results
```bash
[command output here]
```

## Build Results
```bash
[command output here]
```

## Gaps Found
- [ ] Gap 1: [description]
- [ ] Gap 2: [description]

## Fix Plans
- [ ] Fix plan 1: [description]
```

### Common Verification Failures

| Claim | Requires | Not Sufficient |
|-------|----------|----------------|
| Tests pass | Test command output: 0 failures | Previous run, "should pass" |
| Linter clean | Linter output: 0 errors | Partial check, extrapolation |
| Build succeeds | Build command: exit 0 | Linter passing, logs look good |
| Bug fixed | Test original symptom: passes | Code changed, assumed fixed |
| Requirements met | Line-by-line checklist | Tests passing |

### Warning Signs — Validation

- Using "should", "probably", "seems to"
- Expressing satisfaction before verification ("Great!", "Perfect!", "Done!")
- About to commit/push/PR without verification
- Trusting agent success reports
- Relying on partial verification
- Thinking "just this once"

### Rationalization Prevention

| Excuse | Reality |
|--------|---------|
| "Should work now" | RUN the verification |
| "I'm confident" | Confidence ≠ evidence |
| "Just this once" | No exceptions |
| "Linter passed" | Linter ≠ compiler |
| "Agent said success" | Verify independently |
| "I'm tired" | Exhaustion ≠ excuse |
| "Partial check is enough" | Partial proves nothing |

### Rules

1. **Load `requesting-code-review` skill** — pre-commit verification
2. **Run ALL verification commands** — don't skip
3. **Check requirements AND decisions** — not just tests
4. **Create VERIFICATION.md** — document findings with evidence
5. **Create CHECKPOINT.md** — final summary
6. **Update STATE.md** — mark phase complete

---

## Phase 7: Merge & Cleanup

**Goal:** Merge feature branch, cleanup worktree, update docs.

**Closeout reference:** See `references/phase-closeout.md` for the complete end-to-end checklist covering: separating feature files from unrelated changes, STATE.md update, security scan, commit structure, push, project journal entry, and durable memory registration.

### Merge Checklist

- [ ] All tests passing
- [ ] Code review approved
- [ ] No conflicts with main
- [ ] Unrelated/uncommitted changes stashed or moved (check `git status`)
- [ ] Documentation updated
- [ ] `.spec/` archived (move to `.spec/archive/`)
- [ ] Push to remote (`git push`)
- [ ] Project journal entry written

### Phase 6 → Phase 7 handoff

Fixes found during Phase 6 review must be **applied and committed as part of Phase 6** before proceeding to Phase 7. Do not carry review-discovered bugs into the merge step. After fixes:
1. Re-run full test suite (no regressions)
2. Re-run security scan
3. Update STATE.md with fix evidence
4. Only then advance to Phase 7

### Worktree Cleanup

```bash
# If using worktree
cd /main/repo
git checkout main
git merge feature/XX-name
git branch -d feature/XX-name
git worktree remove ../feature-name
```

### Archive `.spec/`

```bash
# Archive completed feature
mkdir -p .spec/archive
mv .spec/01-feature-name .spec/archive/01-feature-name-$(date +%Y%m%d)
```

---

---

## Planning Templates & References

### Implementation Plan Templates

Two plan formats supported — see `references/create-implementation-plan.md`:

| Format | When to Use | Structure |
|--------|-------------|-----------|
| **PD** (`PLAN.md` + checkpoints) | Features using the standard PD format | `plans/<feature>/PLAN.md` |
| **nexus-vellum** (`plan.md` + `checkpoints.md`) | Projects with own plan format | `plans/active/<feature>/plan.md` |

### Bite-Sized Task Writing

Detailed guidance on task granularity (2-5 min each), plan document structure, and TDD-oriented planning — see `references/writing-plans.md`.

## Routing to Sub-Skills

| Phase | Skill to Load | When |
|-------|---------------|------|
| Worktree | `using-git-worktrees` (if available) | Creating isolated worktree |
| Brainstorming | — | Start of any feature |
| Planning | `writing-plans` | Creating PLAN.md |
| Coding | `clean-code` + `executing-plans` | Writing code |
| Domain Modeling | `ddd-development` | Designing entities/VOs |
| Testing | `test-driven-development` | Writing tests |
| Debugging | `systematic-debugging` | Tests failing |
| Review | `requesting-code-review` | Before commit |
| API Design | `api-design` | Designing endpoints, REST patterns |
| Database | `database-patterns` | Migrations, indexing, queries |
| Security | `security-checklist` | Auth, OWASP, secrets |
| Monitoring | `monitoring-observability` | Logging, metrics, alerts |
| Deployment | `deployment-patterns` | CI/CD, feature flags |
| Performance | `performance-patterns` | Caching, profiling |
| Documentation | `documentation-patterns` | READMEs, ADRs, API docs |
| Recipes | `recipes` | Step-by-step combining skills |
| Parallel | `delegate_task` | Backend + Frontend simultaneously |

---

## Example: Full Pipeline

```
User: "Quero criar um sistema de login"

PD Phase 1 (Brainstorming):
  → Pergunta: "Email/senha? OAuth? MFA?"
  → Propõe 2 abordagens
  → Usuário aprova
  → Salva .spec/01-login/SPEC.md

PD Phase 2 (Planning):
  → Quebra em tasks de 2-5 min
  → Salva .spec/01-login/PLAN.md

PD Phase 3 (Structure):
  → Cria .spec/01-login/{backend,frontend,tests}/

PD Phase 4 (Coding):
  → Carrega clean-code
  → Implementa tasks
  → Atualiza status

PD Phase 5 (Testing):
  → Carrega test-driven-development
  → Escreve testes
  → Debuga se necessário

PD Phase 6 (Review):
  → Carrega requesting-code-review
  → Cria CHECKPOINT.md
  → Commit
```

---

## Common Pitfalls

1. **Skipping brainstorming.** Even "simple" tasks need design. The spec can be short, but it MUST exist.

2. **Tasks too large.** Each task should be 2-5 minutes. If it's bigger, split it.

3. **Not updating status.** Keep `.spec/` in sync with reality.

4. **Forgetting to commit.** Commit after each task or logical unit.

5. **Mixing phases.** Don't code before planning is complete.

6. **STATE.md format mismatch.** The parser must handle both `## Phase: 1` and `## Phase\\n1` formats. Always verify STATE.md is readable after generation. See `references/cli-tool-architecture.md` for details.

7. **CI validation requires "When to Use" on ALL skills.** When building or modifying skills, every SKILL.md MUST have a `## When to Use` section. CI validation will fail without it. Check all skills before pushing: `grep -L "When to Use" skills/*/SKILL.md`.

8. **argparse global flags don't inherit to subparsers.** When building Python CLIs with argparse, flags defined on the main parser are NOT available in subcommand parsers. Use `parents=[global_parent]` when creating subparsers:
   ```python
   global_parent = argparse.ArgumentParser(add_help=False)
   global_parent.add_argument("--json", action="store_true")
   parser = argparse.ArgumentParser(parents=[global_parent])
   subparsers = parser.add_subparsers(dest="command")
   sub = subparsers.add_parser("status", parents=[global_parent])  # MUST include parent
   ```
   Without `parents=`, the subparser rejects the flag with "unrecognized arguments".

9. **Subagent timeout leaves dirty state.** When a subagent times out (600s default), it may have partially modified files or changed the working directory. After a timeout: (a) check which files were modified, (b) verify the working directory is valid, (c) handle remaining work manually or dispatch a new subagent. The terminal tool can break if the CWD was changed to a deleted temp directory — use `execute_code` with explicit `os.chdir()` as a workaround.

10. **pytest capsys captures ALL stdout.** When testing CLI output, earlier commands (init, checkpoint) print messages that mix with the command under test. For JSON output tests, use a helper that extracts the FIRST valid JSON block from captured output, not the entire string:
    ```python
    def extract_json(captured_out):
        lines = captured_out.strip().split("\\n")
        for i, line in enumerate(lines):
            if line.strip().startswith("{") or line.strip().startswith("["):
                return json.loads("\\n".join(lines[i:]))
        return None
    ```

12. **`pd init` fails when `.spec/<feature>/` already exists.** If SPEC.md, PLAN.md, and STATE.md were created manually before the CLI was installed, `pd init <feature>` returns `{"error": "Feature '<feature>' already exists."}` because the CLI detects the existing directory and refuses to overwrite. Workaround: skip the init step entirely and use `pd advance --force` to jump into the correct phase. The CLI can only manage features it created.

13. **Advancing through pre-existing phases requires `--force`.** When spec, plan, and structure were completed by hand before the CLI was available, use `pd advance --force` repeatedly until you reach the coding phase. Each `--force` skips the task-completion validation that would fail because the CLI's internal tracker is empty. After reaching the right phase, create a checkpoint with `pd checkpoint --note "description"` to record the manual progress and continue normally.

14. **Worktree branch conflict.** When creating a new branch from one worktree (`git checkout -b feat/x`), git records it as checked out there. Another worktree cannot check out the same branch until the first worktree switches away. Workaround: push the branch to origin first, then create the second worktree from origin.

15. **Migration renumbering during integration.** When merging branches with overlapping migration numbers, keep the earlier branch's numbers and renumber the later branch's migrations sequentially. Never keep duplicate version numbers — use the reserved range strategy (e.g., LLM v77-v78, WhatsApp v79-v80, BSP v81-v83). Update migration tests that hardcode version numbers.

19. **Do not confuse a green slice with a finished plan.** For standing multi-phase goals, a phase checkpoint is only complete after (a) implementation, (b) fresh-eyes review, (c) fixes for confirmed findings, (d) fresh verification, and (e) an explicit record of deferred infrastructure-dependent work. Never report “finalizado” while the plan still has unverified or uncommitted work.

20. **Trust but verify delegated reports.** Subagents may over-report tests or files after partial edits. Before marking a task done, independently check `git status`, file existence, the exact test paths, and rerun the claimed commands. Treat the report as a lead, not proof.

21. **Long standing goals must keep executing across phase boundaries.** When the user says “continuar” or “finalizar todo o plano”, update state and immediately dispatch the next unblocked task. Do not stop at a checkpoint summary. If the tool/session ceiling interrupts execution, report the exact unfinished slice and preserve a resumable checkpoint.

17. **Cross-branch conflict resolution preserves both intents.** When both branches modify the same file, read all three versions (`:1:path`, `:2:path`, `:3:path`), identify which hunks belong to which intent, and preserve both. Never resolve by accepting an entire file from one side — that silently drops the other branch's work.

18. **Save summaries to files by default.** When producing a comprehensive summary, design document, or review report, write it to a file in the relevant directory (`plans/active/<feature>/`, `docs/`, etc.) instead of only outputting in chat. The user will ask "salvou em algum lugar?" if you don't.

14. **Deferred gaps must be documented in the plan, not skipped silently.** When you intentionally defer a sub-task or known limitation (e.g. a field that needs infrastructure plumbing that doesn't exist yet), do not just move on. Document the gap visibly in the plan file (design.md, resumo.md, checkpoints.md) with a clear description and next steps. The schema or contract already accepts the field as optional — document the gap so the next session or reviewer finds it without asking.

15. **Stash pop after interrupted merge.** If you `git stash` doc changes before a merge and the merge fails (conflicts), `git stash pop` does NOT run. The stash remains. After resolving conflicts and committing, you MUST `git stash pop` explicitly. Verify with `git stash list`. Failing to pop means losing the doc changes forever.

## Continuation discipline for standing goals

When the user says to continue a standing multi-phase goal (for example, "continue", "seguir", or "finalizar o plano"), a checkpoint update is not a stopping point. After recording state, immediately execute the next concrete task in the active phase, unless a real blocker requires user input. The response may summarize the checkpoint, but must not end the work loop merely because validation passed.

Treat "continue" or equivalent instructions as execution authorization, not as a request for another status recap. Continue with the next unblocked task unless a real blocker requires user input, and keep the response language aligned with the user's request.

**Operational continuation gate:** after writing a checkpoint, the very next assistant action in the same turn must be an execution tool call for the next unblocked task (for example, a RED test, repository inspection required by that task, or implementation step). Do not send a user-facing summary between phases and wait for another "continue". A phase boundary is internal bookkeeping, not a conversational boundary. If tool/time budget is exhausted, state that execution was interrupted; otherwise keep the loop running until the overall goal is complete or genuinely blocked.

**Anti-pattern: phase-by-phase stopping.** Do not make one assistant turn per phase, boundary, or green test slice. Treat phase checkpoints as internal state writes, not conversational milestones. In the same turn, continue through the next unblocked task and its RED → GREEN → verification loop. Only stop when the overall standing goal is complete, genuinely blocked, or the user explicitly asks to pause. Do not say “the next step is X” unless X has already been started with a tool call in that turn.

Use this loop:
1. Read the active checkpoint and identify the next unblocked task.
2. Execute that task now, preferably with RED → GREEN → focused validation.
3. Run the relevant build/diff gate, then update the checkpoint.
4. Continue until the turn's tool/time budget is exhausted or the plan is complete/blocked.

If a user explicitly asks to update the skill library after the work, capture this continuation behavior here rather than as a one-off task note.

## Security Hardening with Subagents

When PD is applied to security-sensitive infrastructure (auth, WebSockets, gateways, shell/terminal access, Discord permissions, exposed listeners), use a dedicated discovery wave before writing the implementation spec.

### Wave 1: read-only security reconnaissance

Dispatch up to three fresh subagents in parallel, with non-overlapping scopes:

1. **Boundary auditor** — map public/protected REST routes, WebSocket handshakes, middleware behavior, listeners, and fail-open paths.
2. **Integration auditor** — inspect frontend clients, proxies, systemd units, gateway adapters, and compatibility constraints.
3. **Test/operations auditor** — design deterministic RED/GREEN tests, smoke tests, rollback, and post-restart checks.

For Discord or other messaging gateways, replace one lane with a **policy auditor** covering user/channel/role allowlists, mention/thread behavior, and administrative actions. All Wave 1 agents must be read-only: do not edit source, config, services, or restart processes.

### Decision gate before SPEC

Do not write the implementation SPEC until the reconnaissance results are independently checked and any architecture choice with meaningful compatibility impact is surfaced to the user. Typical choices include cookie session vs ephemeral WebSocket ticket, local-only bind vs remote access, and global vs scoped channel permissions. Ask one decision question at a time.

### Preserve active WIP

Before creating a hardening feature, inspect `git status`. Existing uncommitted changes are not scope to absorb, reset, stash, or rewrite implicitly. Do not reuse an unrelated active `.spec/<feature>` directory. Create a separate feature/worktree or remain read-only until the boundary is explicit.

### Hardening acceptance gates

The plan must include executable gates for:

- public health endpoints remaining available;
- unauthenticated REST returning `401` (or explicit fail-closed startup);
- unauthenticated WebSockets rejected before `accept()`;
- session/resource ownership checked after authentication;
- CORS and WebSocket `Origin` allowlists being explicit;
- docs/OpenAPI exposure following an explicit policy;
- listeners bound only to the intended interface;
- gateway users/channels/actions restricted by allowlist;
- restart, health, rollback, and log-redaction smoke tests.

Keep security tests offline and deterministic. Isolate pre-existing provider/OAuth failures from the security gate rather than skipping security assertions conditionally.

### Evidence discipline

Subagent reports are hypotheses until the orchestrator verifies critical claims independently. In particular, tool redaction can make valid source look truncated; run a syntax/import check before treating a file as corrupted. Never print secrets while validating configuration.

A reusable security-hardening test matrix is documented in `references/security-hardening-wave.md`.

## External dependency adoption: audit → PDS → reversible spike

When evaluating an external repository as a possible future dependency or architectural source, do not jump from README enthusiasm to installation. Treat it as an adoption decision with its own branch and evidence trail:

1. Audit the pinned upstream revision, license, runtime, package manager, architecture, integration seams, security docs, tests, and operational surface.
2. Record what was actually verified versus what came only from upstream claims. A passing local audit must name the exact command and environment; missing runtime/tooling is a deferred verification item, not a conclusion about the project.
3. Create an isolated documentation branch/worktree from a clean base. Preserve unrelated WIP worktrees and never install into the active runtime during the research pass.
4. Use a repository-native PDS package with at least: `README.md`, `SPEC.md`, `RESEARCH.md`, `CONTEXT.md`, `PLAN.md`, `STATE.md`, `STATE.json`, `CHECKPOINT.md`, `VERIFICATION.md`, and `DECISIONS.md`.
5. Keep the first adoption phase reversible and low-risk: a disposable runtime/data directory, sanitized fixtures, read-only or shadow mode, fixed baseline comparison, provenance/citation checks, privacy/secret/path checks, export/delete/rebuild verification, and explicit rollback.
6. Integrate through the narrowest stable boundary first (usually local stdio MCP or an adapter) before modifying the core agent, gateway, systemd services, or source-of-truth memory.
7. Commit and push the documentation branch only; do not merge or deploy until the spike, fresh-eyes review, and user adoption gate pass.

The plan must explicitly distinguish:

```text
human source of truth
  → machine index/brain
  → retrieval/synthesis contract
  → agent integration
  → optional remote scale
```

For memory/knowledge systems, preserve the existing human source of truth and prohibit automatic write-back during evaluation. Compare candidates one at a time; do not install two competing memory systems into the same active runtime before a baseline exists. The reusable audit/PDS checklist is in `references/external-repo-adoption.md`.

## Product/AI planning: canonical truth → contextual composition

For AI-assisted products that transform user-owned artifacts (resumes, profiles, documents, messages), model the user artifact as structured canonical claims/evidence rather than a single mutable text blob. Separate:

- **canonical refinement:** improve clarity, evidence, consistency, and positioning without creating facts;
- **contextual composition:** select, prioritize, reorder, and render a version for a target context (job, audience, workflow) without mutating the canonical source.

Every generated change should carry source claims/evidence, reason, confidence, risk, and an accept/edit/reject/ask path. Missing facts become questions; the model must not fill metrics, credentials, seniority, or experience by inference. Contextual outputs must be immutable, versioned packages with input/output hashes, prompt/model version, warnings, and a human approval gate before external side effects.

For a first vertical slice, validate the complete value loop rather than building a broad dashboard: ingest real-shaped input → normalize → map requirements to evidence → compose a contextual artifact → policy-check → human review/approval dry-run. Keep external sending disabled until the dry-run is reproducible and auditable.

See `references/product-ai-pds.md` for the reusable domain model, gate checklist, and SQLite-first persistence guidance. For the complete G0/G1 → contracts → TDD vertical-slice recipe, validator reconciliation, and evidence hygiene, see `references/vertical-slice-pds.md`.

### Vertical-slice execution guardrail

For a new AI-assisted product with a legacy adapter, do not stop after writing a plan or after a green checkpoint when the user says “continuar/seguir”. Close G0 with fresh repository/schema/fixture evidence, grill G1, compile full task envelopes, then execute the next unblocked contract/domain task in the same turn. Use canonical claims/evidence for user-owned artifacts, immutable contextual packages, hostile-input fixtures, and human approval before external effects. A planning CLI's parser is itself a contract: satisfy its required textual markers and rerun `pd validate --deep`; do not use `--force` to conceal stale state or missing evidence.

**Execution evidence learned from a real vertical slice:**

1. Create the isolated target repository before touching product source; if the legacy path resolves to a contaminated Git root, keep it read-only and record the boundary.
2. Compile complete task envelopes for every planned task before dispatch. A short task list in `PLAN.md` is not equivalent to executable Fleet contracts.
3. Reconcile the validator's actual textual contract: `pd validate --deep` may require checkbox-style requirements in `SPEC.md`, a non-empty `tests/` directory under the feature spec, and a literal `## Decisions` heading in `CONTEXT.md`. Fix the artifacts and rerun validation instead of forcing the CLI.
4. Keep planning-state evidence cumulative. When adding a later task, append its RED/GREEN result; do not overwrite earlier evidence or duplicate section headings.
5. Treat a green schema module as distinct from a formal migration gate. If the plan promises Alembic/additive migrations, leave that gate partial until a migration is executable and tested against an existing database shape.
6. For legacy JSON ingestion, inspect the real payload shape with redacted output, preserve raw snapshots separately from normalized rows, and test both same-ID idempotency and different-ID fingerprint deduplication.
7. Fixtures are executable contracts: write real line breaks (not literal `\\n` text), include hostile-input cases as data, and verify the fixture parser itself before relying on downstream security tests.
8. Use strict RED → GREEN per domain slice, then run the full suite, `git diff --check`, `pd validate --deep`, and a clean branch/push gate before marking the checkpoint complete.
9. For product/AI vertical slices, add one integrated smoke test using real-shaped fixtures that traverses ingestion → canonical claims/evidence → contextual composition → policy check → immutable package → human approval dry-run. Assert explicitly that no external dispatch occurred; unit tests alone do not close the vertical-slice gate.
10. Treat safety-policy states separately: a clean local dry-run with external dispatch disabled should be `passed`/approvable locally while retaining `external_send_disabled` as an auditable warning; hostile instructions or prompt injection remain blocking violations.
11. Use the real hostile fixture in an adversarial regression test, not only an invented unit string. Also validate strict domain models against real fixture shape before relying on them; model every required structured section explicitly instead of weakening `extra="forbid"`.
12. If independent fresh-eyes review cannot run, keep the review gate `PARTIAL/BLOCKED` and document the exact transport/provider failure. Manual review, static scans, and green tests are complementary evidence, not an independent approval.
13. If the tool/session ceiling interrupts a standing execution loop, do not present the overall plan as complete. Preserve the exact unfinished test/task, distinguish committed from uncommitted changes, and report the precise resumable command; do not claim a commit or push that was not freshly verified.

See `references/vertical-slice-pds.md` for the reusable G0/G1, validator-reconciliation, fixture, and evidence checklist.

### State reconciliation before a new integration wave

Before starting an adjacent integration wave, reconcile every state artifact against observed code and fresh commands: `PLAN.md` task checkboxes, `STATE.md`, `STATE.json`, `VERIFICATION.md`, fleet/task metadata, and `git status`. Historical summaries and stale checkboxes are not evidence. If they disagree, preserve the most recent verified facts, document partial/deferred tasks explicitly, validate JSON/plan syntax, run the full suite, and commit the reconciliation before adding new work. For external integrations, record the boundary between implemented offline contracts and credential/provider-dependent work; never mark OAuth or live API verification complete without a real authorized probe.

### Existing-project grill: reconciliation before execution

When a user says to “start the grill” on an existing multi-surface project, the first deliverable is a **read-only reconciliation gate**, not new product code. Read the active product/architecture docs, all plan/checkpoint/state variants, current branch/base, modified and untracked paths, and the real test/build commands. Produce a short grill artifact with:

1. the product value loop and canonical baseline;
2. exact fresh verification evidence (backend, frontend, build/typecheck, static/diff checks);
3. contradictions between plans, checkpoints, code, and branch state;
4. blockers/high risks, especially uncommitted WIP, stale state, provider gates, canonical-hash binding, and incomplete browser QA;
5. an ordered next-wave sequence with explicit forbidden side effects.

A green suite proves the observed workspace executes; it does **not** prove the plan is current, the worktree is reproducible, the changes are merge-ready, or external actions are safe. Keep the result `PARTIAL/BLOCKED FOR RECONCILIATION` until the source of truth is chosen and the WIP is inventoried. Preserve unrelated changes; do not reset, clean, stash, commit, push, or merge implicitly. Record “implemented,” “verified,” “deferred,” and “blocked/disabled” as separate labels.

#### Documentation/code freshness gate

When auditing a project that contains an executable CLI or fleet/runtime implementation, reconcile documentation against live behavior before trusting roadmap or status claims:

1. Run the real CLI help/status entrypoint and inventory commands that actually exist.
2. Run the canonical full test suite and record the fresh count, duration, and exit code.
3. Compare those results with README, roadmap, changelog, architecture, plan, and verification artifacts.
4. Flag stale version numbers, test counts, “planned” features that are already implemented, and status labels that disagree across documents.
5. Treat the freshest verified command output as evidence for the current implementation state, but do not silently rewrite documentation or claim release readiness.
6. Report the reconciliation as a documentation/status gap and recommend one canonical status update before the next feature wave.

A passing test count is evidence of executable behavior only; it is not evidence that the documentation is current, the release is production-ready, or external/provider execution is authorized. The reusable output format is: **observed**, **verified**, **stale/contradictory**, **deferred**, and **blocked**.

## External provider integrations: adapter-first, credential-deferred

When a product needs Gmail, Calendar, payments, storage, or another external provider, first audit whether an official CLI/SDK or mature self-hosted integration already covers OAuth, token refresh, and API translation. Do not rebuild credential mechanics before comparing reuse options.

Use this sequence:

1. Compare the official provider tool, a self-hostable integration manager, and direct SDK usage. Separate architectural relevance from adoption readiness, license, data egress, operational weight, and account-switching support.
2. Select the narrowest reusable boundary. For local multi-account Google Workspace, an official CLI adapter can own OAuth/token encryption while the product owns account registry, account selection, policy, audit, and domain relationships.
3. Isolate credentials per account using a project-scoped config/data directory. Never place provider tokens in a global assistant directory, source tree, CandidatePackage, logs, or agent context. Store only account metadata in the product database when the adapter already encrypts credentials.
4. Implement offline contracts first: account model, registry, config-dir selection, safe command runner, timeout/JSON/error handling, and read-only service methods. Test all of these with mocked subprocesses; no credentials are needed.
5. Treat provider authentication and live API probes as a separate, explicitly credential-dependent gate. Mark it `deferred` rather than blocking the local MVP, and do not claim OAuth/API verification without an authorized probe.
6. Keep external writes behind the existing approval gate. Read-only Gmail/Calendar may be integrated before compose/send or event mutation; the latter require separate scopes, tests, idempotency, audit, and human confirmation.
7. Reconcile `PLAN.md`, `STATE.md`, `STATE.json`, and `VERIFICATION.md` before and after adding the integration. Distinguish implemented offline seams from deferred OAuth/provider work.

For the concrete Google Workspace CLI comparison, per-account config pattern, and `gws` probe evidence, see `references/google-workspace-adoption.md`.

## Skill source and installation reconciliation

When a versioned skill repository and installed copies disagree, follow `references/skill-source-reconciliation.md`: inspect every active profile and platform, audit installed-only content before overwriting it, promote accepted improvements into a versioned reconciliation branch, then reinstall and verify all destinations. Installed content is evidence to review, not an implicit source of truth.

## Repository-native planning and scope boundaries

When applying PD to an established repository, the generic CLI is optional. First verify that the repository's native plan structure is compatible with the CLI; if commands report no initialized feature or expect a different state layout, do not force-initialize or create a parallel `.spec/` tree. Use the repository-native design/plan/checkpoint files as the source of truth and record the CLI mismatch as an operational note.

When applying PD to an established repository, the generic `.spec/` layout is guidance, not a mandate. If the project already has a canonical plan shape (for example `plans/active/<feature>/design.md`, `plan.md`, `checkpoints.md`, and `tests.md`), use those files as the specification/plan/state spine and record PD status there. Do not create a parallel planning tree just to satisfy the generic template.

For **multi-branch integration** (assembling a release candidate from independent feature branches), see `references/multi-branch-integration.md`. It covers ordered merge strategy, conflict resolution with intent preservation, migration renumbering, and gap documentation.

For long-running feature work, preserve uncommitted WIP and branch/worktree boundaries. Do not commit, push, create a PR, deploy, or merge as part of implementation unless the user explicitly requests that stage; verification can be complete while delivery remains pending.

When a future initiative is adjacent to the active feature, make the split explicit before coding: preserve the shared seam/interface, name the deferred implementation, and leave the future plan/worktree untouched. Extensibility is not permission to build the second adapter/runtime early.

If the user chooses a new branch for existing uncommitted WIP, preserve the full change set with `git switch -c <branch>` and verify status immediately. Do not reset, stash, split, or discard WIP implicitly; keep the old branch reference until the user decides whether to remove it.

## Verification Checklist

- [ ] SPEC.md exists and is approved
- [ ] PLAN.md exists with bite-sized tasks
- [ ] `.spec/` structure created
- [ ] All tasks have status tracking
- [ ] Code follows `clean-code` principles
- [ ] Tests follow `test-driven-development`
- [ ] CHECKPOINT.md created
- [ ] Delivery stage explicitly approved (commit/push/PR/deploy only when requested)
- [ ] If delivery was approved: all changes committed
- [ ] STATE.json exists and is valid
