# PD Companion (VS Code)

Read-only status and validation for a Project Development workspace.

## Run locally

```bash
cd extensions/vscode
npm install
npm run compile
code --extensionDevelopmentPath="$PWD" /path/to/pd-workspace
```

## Commands

- `PD: Show Status` — read `pd status --json`.
- `PD: Validate` — run `pd validate --json` and print it in the `PD` output channel.
- `PD: Open SPEC` — open `.spec/<feature>/SPEC.md`.

## Settings

- `pd.pythonPath` — Python executable (default `python3`).
- `pd.scriptPath` — path to `pd.py` relative to the workspace (default `scripts/pd.py`).

## Boundary

This extension never mutates `.spec`, never edits files, and never calls the
network. Mutating commands are intentionally out of scope for this slice.
