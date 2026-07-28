# Installer contract

`install.sh` discovers existing platform roots and never creates a root merely to
probe for support. It exits `2` with an explicit error when none is available.

When `$HOME/.hermes` exists, the installer installs the skills under
`$HOME/.hermes/skills/software-development` and the complete CLI runtime under
`$HOME/.hermes/bin/`:

- `pd` (the executable wrapper)
- `pd.py`
- `pd_fleet/` (the Python runtime package)

The CLI destination has its own `.pd-cli-installer-manifest`, listing each file
owned by the installer. On subsequent installs only paths recorded in that CLI
manifest are removed before the current runtime is copied; unrelated files are
not swept. A pre-existing, non-owned `pd`, `pd.py`, or `pd_fleet` path is treated
as a collision and is never overwritten.

OpenCode and Claude are installed only when `$HOME/.config/opencode` and
`$HOME/.claude` already exist, respectively. Each skill destination contains a
`.pd-installer-manifest` owned by this installer. On subsequent installs only
paths recorded in that manifest are removed before current skills are copied;
unrelated files are not swept.
