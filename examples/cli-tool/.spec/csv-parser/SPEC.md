# Specification: CSV Parser CLI Tool

**Tool:** csvtool
**Version:** 0.1.0
**Created:** 2026-06-14

## Overview

`csvtool` is a command-line utility for quickly inspecting, filtering, and transforming CSV files. It prioritizes speed, usability, and beautiful terminal output.

## Requirements

### Core Commands

| Command | Description | Example |
|---------|-------------|---------|
| `info` | Show CSV metadata (rows, columns, types) | `csvtool info data.csv` |
| `head` | Show first N rows | `csvtool head data.csv --rows 5` |
| `filter` | Filter rows by column value | `csvtool filter data.csv --col status --val active` |
| `sort` | Sort by column | `csvtool sort data.csv --col name` |
| `select` | Show only specified columns | `csvtool select data.csv --cols name,email` |
| `export` | Export filtered data to new file | `csvtool export data.csv --format json` |

### Non-Functional
- Process files up to 1GB without loading entirely into memory
- Support common encodings (UTF-8, Latin-1)
- Beautiful terminal output using Rich library
- Helpful error messages with suggestions
- `--help` on every command with examples

## Data Flow

```
CSV File → Parser → Filter/Transform → Formatter → Terminal/File
```

## Out of Scope
- Joining multiple CSV files (Phase 2)
- SQL-like queries (Phase 2)
- Streaming real-time data (Phase 3)
