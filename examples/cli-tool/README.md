# Example: CLI Tool — CSV Parser

This example demonstrates a simpler PD pipeline application: building a command-line CSV parser tool.

## Project Overview

**Tool:** `csvtool` — A fast, user-friendly CSV processing CLI
**Stack:** Python (Click + Rich)
**Feature:** Parse, filter, sort, and transform CSV files from the command line

## Skills Used

| Skill | How It's Used |
|-------|---------------|
| **pd** | Orchestrates the 8-phase pipeline |
| **clean-code** | Maintainable CLI structure |
| **test-driven-development** | Tests written before implementation |
| **writing-plans** | Wave-based task breakdown |

## Why This Example?

CLI tools are a great way to learn PD because:
1. **Small scope** — Easy to complete in one sitting
2. **Clear inputs/outputs** — File in, processed data out
3. **Testable** — Every command can be tested independently
4. **Real-world** — Developers build these all the time

## Pipeline Summary

```
Phase 1: Requirements
  → What CSV operations do we need?
  → Filter, sort, select columns, export

Phase 2: Planning
  → Wave 1: Core parser
  → Wave 2: CLI commands
  → Wave 3: Output formatting

Phase 3: Coding
  → Implement each wave with tests

Phase 4: Polish
  → Error handling, help text, examples
```

## Key Files

- `SPEC.md` — What the tool does
- `PLAN.md` — How we build it (waves)
- `STATE.md` — Current progress

## Quick Start

```bash
# Install the tool
pip install -e .

# Basic usage
csvtool info data.csv
csvtool filter data.csv --column status --value active
csvtool sort data.csv --column name
csvtool select data.csv --columns name,email
csvtool head data.csv --rows 10
```

## Lessons Learned

1. **Start with the happy path** — Get basic parsing working first
2. **Handle errors gracefully** — Bad CSV files are common
3. **Keep output format flexible** — Support table, CSV, JSON output
4. **Document with examples** — CLI users love copy-paste examples
