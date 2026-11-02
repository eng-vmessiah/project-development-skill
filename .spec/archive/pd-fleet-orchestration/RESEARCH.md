# PD Fleet Orchestration — Wave 0 Research

**Date:** 2026-07-16
**Branch:** `feat/pd-fleet-orchestration-plan`
**Status:** complete

## Repository findings

- `scripts/pd.py` is a single-file Python CLI with `PDConfig`, `PDState`, and `PD` command dispatch.
- State is dual-backed by `.spec/<feature>/STATE.json` (preferred) and `STATE.md` (human-readable/migration fallback).
- Existing state has `feature`, `phase`, `status`, `tasks` as completed strings, `checkpoints`, and timestamps.
- Existing CLI commands cover initialization, phase progression, validation, checkpoints, reporting, history, diff, and JSON output.
- `pd.yaml` configures phases, required files, hooks, validation, and output; it has no fleet/task schema yet.
- Existing templates are Markdown-only and model a simple task, checkpoint, and component status.
- Existing tests are concentrated in `tests/test_pd.py`, use pytest fixtures with temporary directories, and assert CLI behavior through `PD.run()`.
- Existing examples use wave headings and Markdown task tables, but no machine-validatable DAG or agent contract.

## Extension points

1. Add a dedicated domain module instead of continuing to grow `scripts/pd.py` blindly.
2. Preserve `PDState` fields and add optional fleet fields for backward compatibility.
3. Add validation functions that can be unit-tested without invoking an agent runtime.
4. Add read-only CLI commands first: fleet status and eligible tasks.
5. Keep dispatch represented by an adapter/protocol; do not make the core depend on Hermes/OpenCode/Claude APIs.
6. Add new templates under `skills/pd/templates/` and copy them from `pd init` only after their contract is stable.

## Current gaps confirmed

- No task IDs or structured dependency edges.
- No cycle detection or path ownership validation.
- No task lifecycle beyond completed string list.
- No agent role/capability assignment.
- No retry, blocker, attempt, or evidence model.
- `advance_phase` currently does not enforce required files despite configuration exposing them.
- `verify` is a reporting command and does not itself return a non-zero failure status for failed checks.
- `scripts/pd` is only a wrapper; all CLI behavior is in `scripts/pd.py`.

## Constraints derived from the repository

- Existing tests and consumers may import `PD`, `PDConfig`, `PDState`, and exception classes from `scripts/pd.py`.
- Existing feature directories must continue loading from old `STATE.json`/`STATE.md` shapes.
- CLI JSON output must remain parseable; tests already account for preceding human output.
- The first implementation should be deterministic and local, with simulated/recorded dispatch rather than external credentials.

## Wave 0 conclusion

The first implementation should be a **local fleet planning and coordination layer**: structured contracts, DAG validation, lifecycle state, eligible-task calculation, read-only inspection, and resumable checkpoints. Actual provider dispatch belongs behind a later adapter and must not be mixed into the first schema/validation change.
