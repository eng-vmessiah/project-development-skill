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

### Hermes Agent
```bash
cp -r skills/* ~/.hermes/skills/software-development/
```

### OpenCode
```bash
cp -r skills/* ~/.config/opencode/skills/
```

### Claude Code
```bash
cp skills/*.md ~/.claude/commands/
```

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
