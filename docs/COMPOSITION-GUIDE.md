# Cross-Skill Composition Guide

PD owns the development lifecycle: phases, artifacts, state, gates, and verification.
Specialist skills add depth inside a phase; they do not replace PD's gates, and they
do not authorize delivery. This guide records the pairings that work and the
handoffs between them.

## Composition rules

1. **One lead skill per phase.** PD leads the pipeline. A specialist becomes the
   lead only for its own bounded activity (for example, `systematic-debugging`
   inside Phase 5), then hands control back to PD.
2. **PD remains the control plane.** Every decision that changes scope, contracts,
   gates, or release state is recorded in `.spec/` and approved through PD.
3. **Load a specialist for a reason.** Use its checklists, patterns, or references
   when the task matches; do not load a library of overlapping workflows "just in
   case".
4. **Specialist output is an artifact.** A threat model, API contract, migration
   plan, or debugging report is an input to the PD phase, not a substitute for the
   phase's evidence.
5. **No double gates.** If a specialist has its own approval step, map it to the PD
   gate that consumes it. Do not create a second, competing gate for the same
   decision.
6. **Record the pairing.** Put the chosen skills and their outputs in `CONTEXT.md`
   so the next session knows why a pattern was applied and where its evidence lives.

## Phase map

| PD phase | Default lead | Add a specialist when |
|---|---|---|
| 0 — Intake and worktree | `pd` | The work needs a spike or a product decision: `spike`, `plan` |
| 1 — Discovery and specification | `pd` | Requirements are ambiguous: `writing-plans`, `plan`; architecture is unfamiliar: `engineering/codebase-design` |
| 2 — Planning | `pd` | The plan needs design-level decomposition: `writing-plans`; parallel execution: `subagent-driven-development` |
| 3 — Structure | `pd` | The module boundary is the question: `ddd-development`, `engineering/codebase-design` |
| 4 — Implementation | `pd` | Code shape/quality: `clean-code`, `design-patterns`; API surface: `api-design`; persistence: `database-patterns`; auth: `auth-patterns`; service wiring: `service-composition` |
| 5 — Testing and debugging | `pd` | Tests first: `test-driven-development`; a hard failure: `systematic-debugging`; flaky or AI-assisted tests: `ai-regression-testing` |
| 6 — Review and verification | `pd` | Independent review: `requesting-code-review`; security-sensitive change: `security-checklist`; performance claim: `performance-patterns` |
| 7 — Delivery | `pd` | Release/deploy mechanics: `deployment-patterns`; observability contract: `monitoring-observability`; docs: `documentation-patterns` |

## Worked compositions

### New feature with unclear scope

**Lead:** `pd` (Phase 1)
**Support:** `spike` to test one uncertainty, `writing-plans` to turn the result into
waves, `plan` if the owner wants a reviewable plan before code.

**Handoff:** the spike produces a measured answer, not a commitment. The answer
becomes a requirement or an explicit non-goal in `SPEC.md`; PD then plans and gates
the implementation. A spike never authorizes implementation by itself.

### API endpoint

**Lead:** `pd`
**Support:** `api-design` for resource/verb/status semantics, `auth-patterns` for the
identity and authorization boundary, `database-patterns` for persistence and
migrations, `security-checklist` before the review gate.

**Handoff:** the API contract and threat model land in `SPEC.md`/`CONTEXT.md`; the
PD review gate checks the contract, not just the tests. If the endpoint changes a
public contract, stop and record the scope change before coding.

### Production bug

**Lead:** `systematic-debugging` for the investigation
**Support:** `pd` for the fix's spec/state/gates, `ai-regression-testing` when the
failure is intermittent or model-assisted, `requesting-code-review` before delivery.

**Handoff:** the debugging report states the root cause and the reproduction. PD
turns the reproduction into a regression test and the fix into a task. Do not let a
"quick fix" bypass the failing-test-first step.

### Refactor or boundary change

**Lead:** `pd`
**Support:** `clean-code` for local shape, `engineering/codebase-design` for module
depth and seams, `test-driven-development` for the behavior-preserving loop,
`requesting-code-review` for an independent read.

**Handoff:** the refactor's acceptance criterion is observable behavior preserved
plus the new boundary; "it looks cleaner" is not a gate. If the refactor changes a
public API, it is a scope change and needs the owner's decision.

### Multi-service change

**Lead:** `pd`
**Support:** `service-composition` for Worker/Function/Trigger wiring,
`monitoring-observability` for logs/metrics/traces, `deployment-patterns` for the
rollout and rollback, `security-checklist` for the new trust boundaries.

**Handoff:** the service contract and failure modes go into the spec; the rollout
and rollback are part of delivery evidence. A local green test does not prove a
live-service change.

### Parallel implementation

**Lead:** `pd` (Phase 2 plan)
**Support:** `subagent-driven-development` for isolated workers,
`engineering/resolving-merge-conflicts` when branches diverge, `requesting-code-review`
for the integrated result.

**Handoff:** split by read-set and file ownership, not by folder. PD owns the
integration gate and the final verification; a worker's self-report is not evidence.

## Anti-patterns

- **Skill stacking:** loading `pd`, `plan`, `writing-plans`, and
  `subagent-driven-development` at once when only one of them should lead the
  phase. Choose the lead first, then add support.
- **Specialist as gate:** treating a security checklist or code-review skill as an
  approval to ship. PD's verification and the owner's gate remain authoritative.
- **Orphan artifact:** producing a threat model or migration plan that never lands
  in `SPEC.md`, `CONTEXT.md`, or `PLAN.md`. The next session cannot consume it.
- **Premature parallelism:** dispatching workers before the plan has disjoint
  read-sets and a single writer for shared files.
- **Debugging by rewrite:** applying `clean-code`/`design-patterns` before
  `systematic-debugging` has established the root cause.

## Quick selection

| If the question is... | Start with |
|---|---|
| "What are we building and why?" | `pd` + `writing-plans`/`spike` |
| "What is the API contract?" | `pd` + `api-design` |
| "Is this secure?" | `pd` + `security-checklist` + `auth-patterns` |
| "Why does it fail?" | `systematic-debugging` + `pd` |
| "How should this be structured?" | `pd` + `engineering/codebase-design` + `ddd-development` |
| "How do we ship it?" | `pd` + `deployment-patterns` + `monitoring-observability` |
| "How do we run this in parallel?" | `pd` + `subagent-driven-development` |

The composition is working when every specialist output has a named PD phase, a
recorded artifact, and a gate that can reject it.
