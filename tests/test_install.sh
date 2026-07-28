#!/bin/bash
# Deterministic installer regression tests. All cases use temporary HOME.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP_DIR=$(mktemp -d)
trap 'rm -rf "$TMP_DIR"' EXIT

# Empty HOME must fail and must not bootstrap any platform root.
empty_home="$TMP_DIR/empty-home"
mkdir -p "$empty_home"
if HOME="$empty_home" bash "$REPO_DIR/install.sh" >"$TMP_DIR/empty.out" 2>&1; then
    printf 'empty HOME unexpectedly succeeded\n' >&2
    exit 1
fi
grep -Fq 'ERROR: no supported destination found' "$TMP_DIR/empty.out"
[[ ! -e "$empty_home/.hermes" && ! -e "$empty_home/.config" && ! -e "$empty_home/.claude" ]]

# Hermes is an existing supported root. Seed an installer manifest containing a
# stale skill, plus unrelated user files that must remain untouched.
hermes_home="$TMP_DIR/hermes-home"
mkdir -p "$hermes_home/.hermes/skills/software-development/stale-skill" \
    "$hermes_home/.hermes/skills/software-development/user-skill" \
    "$hermes_home/.hermes/user-data"
printf 'stale\n' > "$hermes_home/.hermes/skills/software-development/stale-skill/SKILL.md"
printf 'user skill\n' > "$hermes_home/.hermes/skills/software-development/user-skill/notes.txt"
printf 'keep\n' > "$hermes_home/.hermes/user-data/keep.txt"
printf 'dir\tstale-skill\n' > "$hermes_home/.hermes/skills/software-development/.pd-installer-manifest"
HOME="$hermes_home" bash "$REPO_DIR/install.sh" >"$TMP_DIR/hermes.out"

grep -Fq 'CLI installed at' "$TMP_DIR/hermes.out"
[[ ! -e "$hermes_home/.hermes/skills/software-development/stale-skill" ]]
[[ -f "$hermes_home/.hermes/skills/software-development/user-skill/notes.txt" ]]
[[ -f "$hermes_home/.hermes/user-data/keep.txt" ]]

source_count=$(find "$REPO_DIR/skills" -type f -name SKILL.md | wc -l)
installed_count=$(find "$hermes_home/.hermes/skills/software-development" -type f -name SKILL.md | wc -l)
[[ "$installed_count" -eq "$source_count" ]]
[[ -f "$hermes_home/.hermes/skills/software-development/engineering/codebase-design/SKILL.md" ]]
[[ -x "$hermes_home/.hermes/bin/pd" ]]
[[ -f "$hermes_home/.hermes/bin/pd.py" ]]
cli_count=$(find "$hermes_home/.hermes/bin/pd_fleet" -type f -name '*.py' | wc -l)
source_cli_count=$(find "$REPO_DIR/scripts/pd_fleet" -type f -name '*.py' | wc -l)
[[ "$cli_count" -eq "$source_cli_count" ]]

# A second run proves the manifest is refreshed and remains deterministic.
HOME="$hermes_home" bash "$REPO_DIR/install.sh" >"$TMP_DIR/hermes-second.out"
installed_count_again=$(find "$hermes_home/.hermes/skills/software-development" -type f -name SKILL.md | wc -l)
[[ "$installed_count_again" -eq "$source_count" ]]
printf 'installer tests: PASS (skills=%s, pd_fleet=%s)\n' "$source_count" "$source_cli_count"
