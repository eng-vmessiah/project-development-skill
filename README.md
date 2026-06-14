# Project Development Skills

A comprehensive skill ecosystem for AI-assisted software development. Works with **Hermes Agent**, **OpenCode**, and **Claude Code**.

## What's Included

| Skill | Description |
|-------|-------------|
| **pd** | Master orchestrator — full development pipeline |
| **clean-code** | Writing maintainable, readable code |
| **ddd-development** | Domain-Driven Design patterns |
| **test-driven-development** | TDD workflow and patterns |
| **requesting-code-review** | Pre-commit verification |
| **systematic-debugging** | Root cause analysis |
| **ai-regression-testing** | Testing patterns for AI code |
| **humanizer** | Remove AI slop from text |
| **writing-clearly-and-concisely** | Clear, forceful prose |
| **writing-plans** | Implementation planning |
| **subagent-driven-development** | Parallel execution |
| **plan** | Plan mode |
| **spike** | Throwaway experiments |

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
                        ↙ ↘ ↘ ↘ ↘
           clean-code ←→ ddd-development
                ↕              ↕
  test-driven-development ←→ requesting-code-review
                ↕
        systematic-debugging
                
  humanizer ←→ writing-clearly-and-concisely
```

## Philosophy

- **No code without spec + plan** — The Prime Directive
- **Evidence-based completion** — No claims without fresh verification
- **Wave-based execution** — Fresh context for heavy work
- **Bug-driven coverage** — Test where bugs were found

## License

MIT

## Credits

Inspired by:
- **Clean Code** — Robert C. Martin
- **Domain-Driven Design** — Eric Evans, Vaughn Vernon
- **Verification patterns** — Evidence-based validation
- **Wave-based execution** — Fresh context subagents
