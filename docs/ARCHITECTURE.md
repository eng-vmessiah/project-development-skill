# Architecture

How the Project Development Skills ecosystem is organized.

## Overview

```
┌─────────────────────────────────────────────────────────────┐
│                 PROJECT DEVELOPMENT SKILLS                   │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐      │
│  │     pd      │◄──►│  Planning   │◄──►│   Coding    │      │
│  │ (orchestr.) │    │   Skills    │    │   Skills    │      │
│  └──────┬──────┘    └─────────────┘    └─────────────┘      │
│         │                                                    │
│         ▼                                                    │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐      │
│  │   Quality   │◄──►│   Pattern   │◄──►│    AI       │      │
│  │   Skills    │    │   Skills    │    │   Skills    │      │
│  └─────────────┘    └─────────────┘    └─────────────┘      │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

## Skill Layers

### Layer 1: Core (pd)

The master orchestrator that coordinates all other skills.

```
pd
├── Phase 0: Setup (references: spike)
├── Phase 1: Brainstorming
├── Phase 2: Planning (references: plan, writing-plans)
├── Phase 3: Structure
├── Phase 4: Coding (references: subagent-driven-development)
├── Phase 5: Testing (references: test-driven-development, ai-regression-testing)
├── Phase 6: Validation (references: requesting-code-review, systematic-debugging)
└── Phase 7: Merge
```

### Layer 2: Quality

Skills that ensure code quality and correctness.

```
Quality Skills
├── test-driven-development
├── requesting-code-review
├── systematic-debugging
├── ai-regression-testing
└── clean-code
```

### Layer 3: Patterns

Reusable design patterns and architectures.

```
Pattern Skills
├── design-patterns (GoF)
├── auth-patterns
├── service-composition
└── ddd-development
```

### Layer 4: AI

Skills specific to AI-assisted development.

```
AI Skills
├── ai-optimization
└── ai-regression-testing
```

### Layer 5: Communication

Skills for clear writing and documentation.

```
Writing Skills
├── humanizer
├── writing-clearly-and-concisely
└── writing-plans
```

## Cross-Reference Map

```
pd ──────────────────────────────────────┐
│                                        │
├──► clean-code ─────────────────────────┤
│         │                              │
│         ▼                              │
├──► ddd-development ◄───────────────────┤
│         │                              │
│         ▼                              │
├──► design-patterns ◄───────────────────┤
│         │                              │
│         ▼                              │
├──► test-driven-development ◄───────────┤
│         │                              │
│         ▼                              │
├──► requesting-code-review ◄────────────┤
│         │                              │
│         ▼                              │
├──► systematic-debugging ◄──────────────┤
│                                        │
├──► ai-optimization ◄───────────────────┤
│         │                              │
│         ▼                              │
├──► ai-regression-testing ◄─────────────┤
│                                        │
├──► auth-patterns ◄─────────────────────┤
│                                        │
├──► service-composition ◄───────────────┤
│                                        │
├──► humanizer ◄─────────────────────────┤
│         │                              │
│         ▼                              │
└──► writing-clearly-and-concisely ◄─────┘
```

## Data Flow

```
User Request
      │
      ▼
      pd (orchestrator)
      │
      ├──► Phase 1: Brainstorming
      │         │
      │         ▼
      │    SPEC.md
      │
      ├──► Phase 2: Planning
      │         │
      │         ▼
      │    PLAN.md
      │
      ├──► Phase 3: Structure
      │         │
      │         ▼
      │    .spec/ directory
      │
      ├──► Phase 4: Coding
      │         │
      │         ▼
      │    Source code
      │
      ├──► Phase 5: Testing
      │         │
      │         ▼
      │    Tests
      │
      ├──► Phase 6: Validation
      │         │
      │         ▼
      │    VERIFICATION.md
      │
      └──► Phase 7: Merge
                │
                ▼
           Delivered project code
```

This generic PD workflow describes delivery of project artifacts; it does not imply deployment, production readiness, or live runtime activation.

## Platform Compatibility

All skills work across three platforms:

| Platform | Installation | Usage |
|----------|--------------|-------|
| Hermes Agent | `~/.hermes/skills/` | `skill_view(name='...')` |
| OpenCode | `~/.config/opencode/skills/` | `skill_view(name='...')` |
| Claude Code | `~/.claude/commands/` | `/skill-name` |

The install.sh script handles platform-specific differences (e.g., removing `metadata.hermes` for OpenCode/Claude).

## Templates

Templates are stored in `skills/pd/templates/` and provide standardized formats:

- **TASK.md** — Task definition and acceptance criteria
- **CHECKPOINT.md** — Progress checkpoint
- **STATUS.md** — Project status summary

These are copied to the appropriate location during installation.

## PD/Fleet/Hermes architecture boundary

The repository separates workflow decisions from local coordination and concrete
runtime execution:

```text
PD Core
  goal → discovery → SPEC/PLAN → gates → evidence interpretation → delivery decision
       │
       └── optional local coordination
             │
             ▼
PD Fleet
  TaskSpec → DAG/waves → ready/claim → lifecycle/lease → report/evidence → reconcile
       │
       └── future Hermes Gateway Fleet Bridge (observer first; not a live dispatcher)
             │ JSON-RPC/WebSocket/events
             ▼
Hermes Runtime/Gateway
  sessions → events → delegate_task → providers/models → tools/cron/credentials/capabilities

OMH
  workflow patterns and learning reference only; no runtime authority or integration
```

**PD Core** owns the development workflow, plans, gates, evidence interpretation,
and human delivery decisions. **PD Fleet** is an optional local/simulated
coordination protocol and engine for task lifecycle, dependencies, leases, reports,
checkpoints, events, and reconciliation. Fleet does not own cron, provider
execution, credentials, live dispatch, deployment, or production sandboxing.

**Hermes Runtime/Gateway** owns `delegate_task`, sessions, providers, models, tools,
cron, credentials, effective runtime capabilities/policy, and the Gateway event
surfaces used by Hermes clients. A future **Hermes Gateway Fleet Bridge** may consume
those events and associate user-owned sessions with Fleet state. Fleet-owned task
execution remains a separate, deferred authorization; the dashboard is only a
sibling Gateway client and is not an integration dependency.

**OMH is reference-only**: it may inform workflow patterns and learning, but is not
installed, integrated, scheduled, synchronized, or a source of truth.

## Fleet V2 local boundary and recovery

Fleet V2 is local-first and **PARTIAL/OPEN**: parsing, normalization,
reconciliation, checkpointing, and simulation stay within an explicit output root.
Shell, network, credentials, external providers, and live dispatch remain denied;
local simulation must not be represented as production readiness or as a strong
production sandbox. Any future runtime executor/adapters require separate scope,
security evidence, and approval.

Migration keeps V1 state untouched and runs V2 in a separate namespace. Rollback is
stop local dispatch/simulation, invalidate leases, preserve evidence, and restore
the latest valid snapshot; no destructive rewrite of V1 is permitted. No production,
release, or live-runtime claim follows from this local recovery model.
