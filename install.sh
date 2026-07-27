#!/bin/bash
# Project Development Skills — Multi-Platform Installer
# Compatible with Hermes Agent, OpenCode, and Claude Code on Unix-like hosts.

set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILLS_DIR="$REPO_DIR/skills"
HERMES_DIR="$HOME/.hermes/skills/software-development"
OPENCODE_DIR="$HOME/.config/opencode/skills"
CLAUDE_DIR="$HOME/.claude/commands"

declare -A CLAUDE_SOURCES=()

strip_hermes_metadata() {
    python3 - "$1" <<'PY'
from pathlib import Path
import re
import sys

path = Path(sys.argv[1])
content = path.read_text()
content = re.sub(
    r"metadata:\n  hermes:\n    tags: \[.*?\]\n    related_skills: \[.*?\]\n",
    "",
    content,
    count=1,
)
path.write_text(content)
PY
}

strip_claude_optional_references() {
    python3 - "$1" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
lines = path.read_text().splitlines(keepends=True)
# Claude receives a flat command. Remove optional reference pointers that have
# no corresponding sibling files in ~/.claude/commands.
path.write_text(''.join(line for line in lines if 'references/' not in line))
PY
}

preflight_flat_names() {
    local skill_file skill_dir skill_name
    while IFS= read -r -d '' skill_file; do
        skill_dir="$(dirname "$skill_file")"
        skill_name="$(basename "$skill_dir")"
        if [[ -n "${CLAUDE_SOURCES[$skill_name]:-}" && "${CLAUDE_SOURCES[$skill_name]}" != "$skill_dir" ]]; then
            printf 'ERROR: Claude flat-name collision for %q:\n  %s\n  %s\n' \
                "$skill_name" "${CLAUDE_SOURCES[$skill_name]}" "$skill_dir" >&2
            exit 1
        fi
        CLAUDE_SOURCES[$skill_name]="$skill_dir"
    done < <(find "$SKILLS_DIR" -type f -name SKILL.md -print0)
}

install_hermes() {
    local skill_dir="$1" relative_dir
    relative_dir="${skill_dir#"$SKILLS_DIR"/}"
    relative_dir="${relative_dir%/}"
    mkdir -p "$HERMES_DIR/$(dirname "$relative_dir")"
    rm -rf "$HERMES_DIR/$relative_dir"
    cp -a "$skill_dir" "$HERMES_DIR/$relative_dir"
}

install_opencode() {
    local skill_dir="$1" relative_dir
    relative_dir="${skill_dir#"$SKILLS_DIR"/}"
    relative_dir="${relative_dir%/}"
    mkdir -p "$OPENCODE_DIR/$(dirname "$relative_dir")"
    rm -rf "$OPENCODE_DIR/$relative_dir"
    cp -a "$skill_dir" "$OPENCODE_DIR/$relative_dir"
    strip_hermes_metadata "$OPENCODE_DIR/$relative_dir/SKILL.md"
}

install_claude() {
    local skill_dir="$1" skill_name
    skill_name="$(basename "$skill_dir")"
    mkdir -p "$CLAUDE_DIR"
    # Claude commands are flat and self-contained. Optional references are
    # removed from the rendered command; directory platforms receive them.
    cp "$skill_dir/SKILL.md" "$CLAUDE_DIR/$skill_name.md"
    strip_hermes_metadata "$CLAUDE_DIR/$skill_name.md"
    strip_claude_optional_references "$CLAUDE_DIR/$skill_name.md"
}

run_for_each_skill() {
    local installer="$1" skill_file skill_dir
    while IFS= read -r -d '' skill_file; do
        skill_dir="$(dirname "$skill_file")"
        "$installer" "$skill_dir"
    done < <(find "$SKILLS_DIR" -type f -name SKILL.md -print0)
}

echo "🚀 Project Development Skills Installer"
echo "========================================"
preflight_flat_names

if [ -d "$HOME/.hermes" ]; then
    echo "📦 Installing to Hermes Agent..."
    run_for_each_skill install_hermes
    echo "   ✅ Done"
fi

if [ -d "$HOME/.config/opencode" ]; then
    echo "📦 Installing to OpenCode..."
    run_for_each_skill install_opencode
    echo "   ✅ Done"
fi

if [ -d "$HOME/.claude" ]; then
    echo "📦 Installing to Claude Code..."
    run_for_each_skill install_claude
    echo "   ✅ Done"
fi

echo ""
echo "✅ Installation complete"
echo "Source: $SKILLS_DIR"
echo ""
echo "Usage:"
echo "  Hermes/OpenCode: skill_view(name='pd')"
echo "  Claude: /pd"
