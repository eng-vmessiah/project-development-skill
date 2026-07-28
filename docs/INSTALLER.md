# Installer contract

`install.sh` discovers existing platform roots and never creates a root merely to
probe for support. It exits `2` with an explicit error when none is available.

When `$HOME/.hermes` exists, the installer installs the skills under
`$HOME/.hermes/skills/software-development` and the complete CLI runtime under
`$HOME/.hermes/bin/`:

- `pd` (the executable wrapper)
- `pd.py`
- `pd_fleet/` (the Python runtime package)

OpenCode and Claude are installed only when `$HOME/.config/opencode` and
`$HOME/.claude` already exist, respectively. Each skill destination contains a
`.pd-installer-manifest` owned by this installer. On subsequent installs only
paths recorded in that manifest are removed before current skills are copied;
unrelated files are not swept.
