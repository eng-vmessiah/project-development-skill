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
           Production code
```

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

## Fleet V2 boundary and recovery

Fleet V2 is local-first and **PARTIAL/OPEN**: parsing, normalization,
reconciliation, checkpointing, and simulation stay within an explicit output root.
Shell, network, credentials, and external providers are denied by default. An
opt-in executor requires exact argv allowlists, sandbox/root containment, timeout,
bounded redacted output, leases, and CAS. Threats include untrusted plans,
traversal/symlink escape, stale ownership, crashes, and secret leakage.

Migration keeps V1 state untouched and runs V2 in a separate namespace. Rollback is
stop dispatch, invalidate leases, preserve evidence, and restore the latest valid
snapshot; no destructive rewrite of V1 is permitted.
