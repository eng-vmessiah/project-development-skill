---
name: pd
description: "Use when starting any software development project or feature. Orchestrates the full development pipeline: brainstorming → planning → .spec/ structure → coding → testing → review. Routes to appropriate sub-skills at each phase."
version: 1.0.0
author: ISIS
license: MIT
metadata:
  hermes:
    tags: [project-development, pipeline, orchestration, brainstorming, planning, spec, workflow]
    related_skills: [ai-regression-testing, clean-code, ddd-development, humanizer, requesting-code-review, systematic-debugging, test-driven-development, writing-clearly-and-concisely, writing-plans]
---

# Project Development (PD) — Development Pipeline

## Overview

PD is the **master orchestrator** for software development. It guides you through a complete pipeline from idea to code review, ensuring quality at every step.

**Inspired by:** brainstorming, planning, verification patterns + Context Rot, Wave-Based Execution, STATE.md persistence
**Adapted for:** Hermes Agent + OpenCode + Claude Code

## When to Use

- Starting a new project or feature
- User says: "quero criar", "vamos implementar", "nova feature"
- Any coding task that needs planning before implementation
- Multi-file features, cross-cutting refactors, work spanning hours/sessions

## When NOT to Use (Quick/Fast Tasks)

**Skip the full pipeline if:**
- Task can be fully specified in a single, short prompt
- Completed in one agent turn without clarification
- Variable rename, typo fix, missing import
- Simple bug fix with obvious cause

**Use these instead:**
- `/pd-quick` — ad-hoc work (<2 min)
- `/pd-fast` — small changes (<10 min)

**Rule of thumb:** If the task needs research, involves files you haven't read recently, or depends on decisions not yet settled → use the full pipeline.

## 🚨 BLOCKER — DO NOT CODE FIRST

**Before writing ANY code, you MUST complete:**
1. Brainstorming (understand the problem)
2. Planning (define the approach)
3. Create `.spec/` structure

**There are NO exceptions.** Even "simple" tasks need a brief design.

---

## The Prime Directive

```
NO SPECIFICATION + PLAN, NO CODE
```

If you haven't completed brainstorming and planning, you cannot write code.

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

### Merge Checklist

- [ ] All tests passing
- [ ] Code review approved
- [ ] No conflicts with main
- [ ] Documentation updated
- [ ] `.spec/` archived (move to `.spec/archive/`)

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

## Verification Checklist

- [ ] SPEC.md exists and is approved
- [ ] PLAN.md exists with bite-sized tasks
- [ ] `.spec/` structure created
- [ ] All tasks have status tracking
- [ ] Code follows `clean-code` principles
- [ ] Tests follow `test-driven-development`
- [ ] CHECKPOINT.md created
- [ ] All changes committed
