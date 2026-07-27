# Project Development Skills

A comprehensive skill ecosystem for AI-assisted software development. Works with **Hermes Agent**, **OpenCode**, and **Claude Code**.

## What's Included

| Skill | Description | Size |
|-------|-------------|------|
| **pd** | Master orchestrator — full development pipeline | 34k |
| **clean-code** | Writing maintainable, readable code | 16k |
| **ddd-development** | Domain-Driven Design patterns | 15k |
| **design-patterns** | GoF 23 patterns + decision trees | 19k |
| **auth-patterns** | JWT, OAuth, RBAC, sessions | 11k |
| **ai-optimization** | Prompt/code optimization with reflection | 13k |
| **ai-regression-testing** | Testing patterns for AI code | 4k |
| **service-composition** | Worker-Function-Trigger patterns | 18k |
| **test-driven-development** | TDD workflow and patterns | 10k |
| **requesting-code-review** | Pre-commit verification | 8k |
| **systematic-debugging** | Root cause analysis | 10k |
| **humanizer** | Remove AI slop from text | 1k |
| **writing-clearly-and-concisely** | Clear, forceful prose | 3k |
| **writing-plans** | Implementation planning | 7k |
| **plan** | Plan mode | 9k |
| **spike** | Throwaway experiments | 9k |
| **subagent-driven-development** | Parallel execution via subagents | 12k |

## Quick Install

```bash
git clone https://github.com/your-username/project-development-skill.git
cd project-development-skill
chmod +x install.sh
./install.sh
```

The installer auto-detects which platforms you have installed.

## Manual Installation

Use the repository installer so nested skills, platform transformations, stale-file cleanup, and Claude flat-name collisions are handled consistently:

```bash
chmod +x install.sh
./install.sh
```

For a custom platform, reproduce the contracts in `skills/pd/references/multi-platform-skill-development.md`; do not copy `skills/*.md` because each skill lives in its own directory and may contain references/templates.

## Usage

### Hermes / OpenCode
```
skill_view(name='pd')
```

### Claude Code
```
/pd
```

## The PD Pipeline

```
Phase 0: Setup (worktree)
    ↓
Phase 1: Brainstorming
    ↓
Phase 2: Planning (.spec/)
    ↓
Phase 3: Structure (.templates/)
    ↓
Phase 4: Coding (wave-based)
    ↓
Phase 5: Testing (TDD + bug-driven)
    ↓
Phase 6: Validation (evidence-based)
    ↓
Phase 7: Merge & Deploy
```

## Skill Ecosystem

```
                         pd (master)
                        ↙ ↘ ↘ ↘ ↘ ↘
           clean-code ←→ ddd-development ←→ design-patterns
                ↕              ↕                    ↕
  test-driven-development ←→ requesting-code-review
                ↕
        systematic-debugging
                
  humanizer ←→ writing-clearly-and-concisely
  
  ai-optimization ←→ ai-regression-testing
  
  auth-patterns ←→ service-composition
```

## Philosophy

- **No code without spec + plan** — The Prime Directive
- **Evidence-based completion** — No claims without fresh verification
- **Wave-based execution** — Fresh context for heavy work
- **Bug-driven coverage** — Test where bugs were found

## Templates

The `pd` skill includes templates for:
- `TASK.md` — Task definition
- `CHECKPOINT.md` — Progress checkpoint
- `STATUS.md` — Project status

These are installed to:
- Hermes: `~/.hermes/skills/software-development/pd/templates/`
- OpenCode: `~/.config/opencode/skills/pd/templates/`

## Fleet Orchestration Evolution

The next PD evolution is specified in:

- [`docs/PD-AS-IS-TO-BE.md`](docs/PD-AS-IS-TO-BE.md) — current state, target state, gaps, and migration strategy
- [`docs/PD-FLEET-ORCHESTRATION-PLAN.md`](docs/PD-FLEET-ORCHESTRATION-PLAN.md) — waves, agent roles, contracts, gates, and implementation order
- [`docs/PD-FIRST-CASE-PROMPT.md`](docs/PD-FIRST-CASE-PROMPT.md) — execution prompt for implementing the first case

This proposal evolves PD from a phase-oriented development guide into a protocol for supervised subagent fleets while preserving the simple single-agent flow.

The offline fleet example (`examples/pd-fleet/run_local.py`) performs a validated G1
preflight before creating output files. Gate references are deterministic identities
(`evidence:<task-id>` and `report:<task-id>`) resolved against validated records;
unresolved references fail closed. Output paths are resolved and contained beneath
`--output`, existing symlink roots are rejected, and task IDs must match
`[A-Za-z0-9_-]+` as one safe path segment.

### Fleet V2: local-first and fail-closed

Fleet V2 is **MERGED as experimental/local** in `main`; it is not an operational
production release. The human approval authorizes this merge scope only. The safe
default is local simulation with an explicit plan and output directory; no shell,
network, external provider, credentials, or undeclared validation command is invoked.
External execution requires exact argv allowlist, containment/sandbox, timeout,
redacted bounded output, and a separate explicit release decision. Migration
preserves V1 state and uses a separate V2 namespace/output; rollback stops dispatch, invalidates leases, and restores the last valid snapshot without rewriting V1. Threats
include malicious paths, symlink/traversal, stale leases, concurrent ownership,
secret-bearing output, and provider escape; containment, CAS, redaction, atomic
checkpoints, and default-deny are the controls. The implemented offline checker
`scripts/pd_fleet/v2_doc_paths.py` validates V2 path/link declarations and fails
closed on root/document symlinks; a valid checker result does not authorize external
provider dispatch or a production release.

## License

MIT

## Credits

Inspired by:
- **Clean Code** — Robert C. Martin
- **Domain-Driven Design** — Eric Evans, Vaughn Vernon
- **Design Patterns (GoF)** — Gamma, Helm, Johnson, Vlissides
- **GEPA** — Reflective optimization patterns
- **iii** — Service composition primitives
- **Verification patterns** — Evidence-based validation
