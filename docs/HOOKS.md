# Lifecycle Hooks

`pd.yaml` in the project root (or `~/.pd.yaml` for defaults) can run shell commands
around lifecycle operations:

```yaml
hooks:
  before_advance:
    - "scripts/pre-advance.sh"
  after_advance:
    - "printf 'advanced\n' >> .pd-hooks.log"
  before_checkpoint: []
  after_checkpoint: []
  before_verify:
    - "printf 'verify start\n' >> .pd-hooks.log"
  after_verify:
    - "printf 'verify end\n' >> .pd-hooks.log"
```

## Semantics

- Commands run through the shell with the feature directory as their working
  directory (`.spec/<feature>/`).
- Each hook is bounded to **30 seconds**. A timeout prints a warning and the
  operation continues.
- A non-zero exit prints a warning and the operation continues; hooks are
  advisory, not gates.
- `before_advance`/`after_advance` run on `pd advance`; `before_advance` is skipped
  with `--force`.
- `before_checkpoint`/`after_checkpoint` run on `pd checkpoint`.
- `before_verify`/`after_verify` run on `pd verify`, before and after the checks.
- A malformed `hooks` entry (not a list of non-empty strings) fails closed with a
  configuration error.

## Trust boundary

Hooks are arbitrary shell commands executed with your user privileges. Only put
trusted commands in a project or home config, and do not copy a `pd.yaml` from an
untrusted repository without reading it. Hooks do not run inside a sandbox and do
not inherit any restriction from the PD gates.

## What this does not do

- It does not provide a Python plugin API.
- It does not make a failed hook block delivery; use a gate or a required test for
  that.
- It does not ship hook scripts; keep them in your repository and reference them
  with a path relative to the feature directory or an absolute path.
