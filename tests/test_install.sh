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
[[ -f "$hermes_home/.hermes/bin/.pd-cli-installer-manifest" ]]
grep -Fqx $'file\tpd' "$hermes_home/.hermes/bin/.pd-cli-installer-manifest"
grep -Fqx $'file\tpd.py' "$hermes_home/.hermes/bin/.pd-cli-installer-manifest"
grep -Fq $'file\tpd_fleet/' "$hermes_home/.hermes/bin/.pd-cli-installer-manifest"
cli_count=$(find "$hermes_home/.hermes/bin/pd_fleet" -type f -name '*.py' | wc -l)
source_cli_count=$(find "$REPO_DIR/scripts/pd_fleet" -type f -name '*.py' | wc -l)
[[ "$cli_count" -eq "$source_cli_count" ]]

# A second run proves the manifest is refreshed and remains deterministic.
HOME="$hermes_home" bash "$REPO_DIR/install.sh" >"$TMP_DIR/hermes-second.out"
installed_count_again=$(find "$hermes_home/.hermes/skills/software-development" -type f -name SKILL.md | wc -l)
[[ "$installed_count_again" -eq "$source_count" ]]

# CLI ownership: stale installer-owned files are removed, but unrelated files
# and files added to the package directory survive an upgrade.
cli_dir="$hermes_home/.hermes/bin"
printf 'stale CLI\n' > "$cli_dir/stale-cli.py"
printf 'user CLI\n' > "$cli_dir/user-tool"
printf 'user package file\n' > "$cli_dir/pd_fleet/user_tool.py"
printf 'file\tstale-cli.py\n' >> "$cli_dir/.pd-cli-installer-manifest"
HOME="$hermes_home" bash "$REPO_DIR/install.sh" >"$TMP_DIR/hermes-third.out"
[[ ! -e "$cli_dir/stale-cli.py" ]]
[[ -f "$cli_dir/user-tool" && -f "$cli_dir/pd_fleet/user_tool.py" ]]

# A pre-existing CLI path is never overwritten.
collision_home="$TMP_DIR/collision-home"
mkdir -p "$collision_home/.hermes/bin"
printf 'user-owned pd\n' > "$collision_home/.hermes/bin/pd"
if HOME="$collision_home" bash "$REPO_DIR/install.sh" >"$TMP_DIR/collision.out" 2>&1; then
    printf 'CLI collision unexpectedly succeeded\n' >&2
    exit 1
fi
grep -Fq 'refusing to overwrite non-owned Hermes CLI path' "$TMP_DIR/collision.out"
grep -Fq 'user-owned pd' "$collision_home/.hermes/bin/pd"

# A pre-existing pd_fleet path is also a collision, including a directory.
fleet_collision_home="$TMP_DIR/fleet-collision-home"
mkdir -p "$fleet_collision_home/.hermes/bin/pd_fleet"
printf 'user-owned package\n' > "$fleet_collision_home/.hermes/bin/pd_fleet/keep.py"
if HOME="$fleet_collision_home" bash "$REPO_DIR/install.sh" >"$TMP_DIR/fleet-collision.out" 2>&1; then
    printf 'pd_fleet collision unexpectedly succeeded\n' >&2
    exit 1
fi
grep -Fq 'refusing to overwrite non-owned Hermes CLI path' "$TMP_DIR/fleet-collision.out"
[[ -f "$fleet_collision_home/.hermes/bin/pd_fleet/keep.py" ]]

printf 'installer tests: PASS (skills=%s, pd_fleet=%s)\n' "$source_count" "$source_cli_count"
