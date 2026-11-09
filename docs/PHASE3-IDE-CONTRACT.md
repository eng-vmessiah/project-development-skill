# Phase 3 — IDE Integration Contract (Slice 1)

**Status:** proposed
**Date:** 2026-11-09
**Scope:** one read-only VS Code companion. JetBrains, Vim/Neovim, registry, and
versioned dependencies remain future slices.

## Decision

Start Phase 3 with the smallest integration that proves the contract:

> A VS Code extension that reads PD state through `pd status --json` / `pd validate
> --json` and exposes it in the editor. It never mutates `.spec`, never edits
> files, and never calls the network.

This is deliberately read-only. `advance`, `checkpoint`, `complete-task`, and
`delete` stay in the CLI until the read path is proven and the JSON contract has
tests.

## Why VS Code first

- VS Code is already installed on the reference machine.
- The extension host can invoke the existing Python CLI without a new server.
- A read-only surface validates the JSON contract and error handling without
  putting workflow state at risk.
- It creates a reusable pattern for a later JetBrains/Vim client.

## User-visible behavior

1. On activation in a workspace with `scripts/pd.py` and a `.spec/` directory, a
   status-bar item shows `PD: <feature> P<phase>/<total> · <done>/<total> tasks`.
2. `PD: Show Status` re-reads the status and shows a short information message.
3. `PD: Validate` runs `pd validate --json`, writes the raw result to the `PD`
   output channel, and reports pass/fail.
4. `PD: Open SPEC` opens `.spec/<feature>/SPEC.md` for the active feature.
5. If the CLI, workspace, or feature is missing, the extension shows an actionable
   error instead of crashing or creating files.

## CLI contract

The extension consumes this existing command:

```bash
python3 scripts/pd.py status --json
```

Required fields:

| Field | Type | Use |
|---|---|---|
| `feature` | string | status bar and SPEC path |
| `phase` | number | status bar |
| `phase_name` | string | tooltip |
| `total_phases` | number | status bar |
| `phase_pct` | number | tooltip |
| `status` | string | tooltip |
| `tasks_done` | number | status bar |
| `tasks_total` | number | status bar |
| `tasks_pct` | number | tooltip |
| `checkpoints` | number | tooltip |
| `created_at` | string | tooltip |
| `updated_at` | string | tooltip |

`pd validate --json` may return a list or object; the extension treats it as
opaque JSON for display. It does not reinterpret validation rules in TypeScript.

## Security and trust boundary

- Use `child_process.execFile` with an argument array; never `shell: true` and
  never interpolate user input into a command string.
- The extension passes only `status`/`validate` and `--json`; it has no command
  that mutates state.
- The Python executable and `pd.py` path are user-configurable workspace settings.
  Treat them as trusted local configuration, like `pd.yaml` hooks.
- No telemetry, no network calls, no automatic installs, and no reading of
  credentials.
- The extension displays error text from the CLI; it does not execute it.

## Acceptance criteria

- **AC1:** In a workspace with `scripts/pd.py` and `.spec/`, activation shows a
  status bar item with the feature, phase, and task counts from `status --json`.
- **AC2:** `PD: Show Status`, `PD: Validate`, and `PD: Open SPEC` are registered
  and callable from the Command Palette.
- **AC3:** Missing CLI/workspace/feature produces a VS Code error message and no
  file writes.
- **AC4:** `status --json` parsing rejects malformed payloads with a clear error.
- **AC5:** `npm test` covers the parser and command resolver without requiring a
  VS Code host.
- **AC6:** CI compiles and tests the extension on Node 22; the Python suite and
  release preflight remain green.
- **AC7:** The extension performs no state mutation; the only writes are build
  artifacts under `extensions/vscode/out/`.

## Out of scope

- `advance`, `checkpoint`, `complete-task`, `delete`, or any state mutation.
- Editing SPEC/PLAN/CONTEXT from the editor.
- JetBrains, Vim/Neovim, or a shared language server.
- Marketplace publication, telemetry, authentication, or remote execution.
- Registry, versioned skill dependencies, and project-management integrations.

## Risks

| Risk | Mitigation |
|---|---|
| Status JSON drifts | Parser rejects malformed payloads; Python tests own the schema. |
| CLI path differs per OS | `pd.pythonPath` and `pd.scriptPath` settings; no shell. |
| Extension adds Node to CI | Isolated job, `npm ci`, Node 22; Python jobs unchanged. |
| Read-only surface feels limited | Ship the read path first; mutation is a separate slice with its own review. |

## Next

Implementation plan:
`docs/plans/2026-11-09-vscode-companion.md`.
