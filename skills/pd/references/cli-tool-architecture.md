# PD CLI Tool Architecture

## Overview

The PD CLI provides deterministic workflow management while the LLM provides flexibility and decision-making. This hybrid approach ensures:
- State is persisted in STATE.md (not dependent on LLM memory)
- Validation is enforced by code (not LLM compliance)
- LLM still handles creative decisions and subagent spawning

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        CLI (pd)                             │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐       │
│  │   init  │  │ validate│  │ status  │  │verify   │       │
│  └────┬────┘  └────┬────┘  └────┬────┘  └────┬────┘       │
│       │            │            │            │             │
│       ▼            ▼            ▼            ▼             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              STATE.md (persistente)                 │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                    LLM (via skill)                          │
│  → LLM lê STATE.md                                         │
│  → LLM decide próximas ações                               │
│  → LLM chama delegate_task()                               │
└─────────────────────────────────────────────────────────────┘
```

## Commands

| Command | Description | State Change | Flags |
|---------|-------------|--------------|-------|
| `pd init <feature>` | Initialize new feature | Creates .spec/ structure | — |
| `pd status` | Show current status | Read-only | `-f`, `--json` |
| `pd validate` | Validate progress | Read-only | `--deep`, `--json` |
| `pd checkpoint` | Create checkpoint | Adds to checkpoints list | `--note`, `--json` |
| `pd verify` | Verify before completing | Read-only | `--json` |
| `pd advance` | Advance to next phase | Increments phase | `--dry-run`, `--force`, `--json` |
| `pd complete-task` | Mark task complete | Adds to tasks list | `--json` |
| `pd config` | Show configuration | Read-only | `--json` |
| `pd list` | List all features | Read-only | `--json` |
| `pd delete <feature>` | Delete/archive feature | Removes .spec/ dir | `--archive`, `--force` |
| `pd history` | Show checkpoint timeline | Read-only | `-f`, `--json` |
| `pd report` | Generate progress report | Read-only | `-f`, `--json` |
| `pd diff` | Changes since last checkpoint | Read-only | `-f`, `--json` |
| `pd completion <shell>` | Generate shell completions | Read-only | bash/zsh/fish |

### Global Flags (inherited by ALL subcommands)

| Flag | Description |
|------|-------------|
| `-f`, `--feature` | Target a specific feature (default: most recent) |
| `--json` | Output as JSON instead of human-readable text |
| `--dry-run` | Show what would happen without changing state |
| `--force` | Skip confirmation prompts and validation checks |
| `--no-color` | Disable colored output |

### STATE.json Backend

Dual storage: STATE.json (structured) + STATE.md (human-readable).
On first load of existing features, auto-migrates from STATE.md → STATE.json.
All state changes write both files.

## Config File (pd.yaml)

Place in project root or ~/.pd.yaml:

```yaml
# Phases configuration
phases:
  - id: 0
    name: Setup
    description: Initialize worktree and project
  - id: 1
    name: Brainstorming
    description: Understand the problem
  # ... more phases

# Hooks configuration
hooks:
  before_advance: []
  after_advance: []
  before_checkpoint: []
  after_checkpoint: []
  before_verify: []
  after_verify: []

# Validation rules
validation:
  require_all_requirements: true
  require_tests: true
  require_verification: true
```

## Hooks System

Hooks allow running custom scripts before/after phase transitions:

```yaml
hooks:
  after_advance:
    - "echo 'Advanced to new phase'"
    - "./scripts/run-tests.sh"
  before_verify:
    - "./scripts/lint.sh"
```

## Testing

Run tests with:
```bash
pytest tests/ -v
```

49 tests covering:
- Init, status, validate, advance, checkpoint, complete-task, verify, config
- List, delete, history, report, diff, completion
- Global flags: --json, -f, --dry-run, --force
- STATE.json dual backend
- Multiple features coexistence

### Testing Pitfalls

**Argparse global flags:** Python argparse does NOT inherit parent parser flags
to subparsers automatically. Use `parents=[global_parent]` when creating
subparsers so global flags (-f, --json, --dry-run, --force) work regardless
of argument position. Also: if a subparser defines its own `--force`, remove
it — the parent's `--force` will conflict.

**pytest capsys mixed output:** `capsys.readouterr().out` captures ALL stdout
from the entire test function, not just the last command. When testing JSON
output after `pd init` (which prints emoji messages), use an `extract_json()`
function that finds the FIRST `{` or `[` line and parses from there.

## STATE.md Parsing

**Pitfall:** STATE.md format must be consistent between generation and parsing.

Generated format:
```markdown
## Phase
1 (Brainstorming)
```

Parser must handle both:
- `## Phase: 1 (Brainstorming)` (with colon)
- `## Phase\n1 (Brainstorming)` (colonless, value on next line)

See `_parse_state()` in scripts/pd.py for implementation.
