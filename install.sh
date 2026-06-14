#!/bin/bash
# Project Development Skills — Multi-Platform Installer
# Compatible with: Hermes Agent, OpenCode, Claude Code

set -e

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILLS_DIR="$REPO_DIR/skills"

echo "🚀 Project Development Skills Installer"
echo "========================================"
echo ""

# Detect platforms
HERMES_DIR="$HOME/.hermes/skills/software-development"
OPENCODE_DIR="$HOME/.config/opencode/skills"
CLAUDE_DIR="$HOME/.claude/commands"

INSTALLED=()

# Install to Hermes
if [ -d "$HOME/.hermes" ]; then
    echo "📦 Installing to Hermes Agent..."
    mkdir -p "$HERMES_DIR"
    
    for skill_dir in "$SKILLS_DIR"/*/; do
        skill_name=$(basename "$skill_dir")
        mkdir -p "$HERMES_DIR/$skill_name"
        cp -r "$skill_dir"* "$HERMES_DIR/$skill_name/"
    done
    
    INSTALLED+=("Hermes")
    echo "   ✅ Done"
fi

# Install to OpenCode
if [ -d "$HOME/.config/opencode" ]; then
    echo "📦 Installing to OpenCode..."
    mkdir -p "$OPENCODE_DIR"
    
    for skill_dir in "$SKILLS_DIR"/*/; do
        skill_name=$(basename "$skill_dir")
        mkdir -p "$OPENCODE_DIR/$skill_name"
        
        # Copy SKILL.md and remove metadata.hermes section
        python3 -c "
import re

with open('$skill_dir/SKILL.md', 'r') as f:
    content = f.read()

# Remove metadata.hermes section
content = re.sub(
    r'(metadata:\n  hermes:\n    tags: \[.*?\]\n    related_skills: \[.*?\]\n)',
    '',
    content
)

with open('$OPENCODE_DIR/$skill_name/SKILL.md', 'w') as f:
    f.write(content)
"
        
        # Copy templates if they exist
        if [ -d "$skill_dir/templates" ]; then
            mkdir -p "$OPENCODE_DIR/$skill_name/templates"
            cp -r "$skill_dir/templates"* "$OPENCODE_DIR/$skill_name/templates/"
        fi
    done
    
    INSTALLED+=("OpenCode")
    echo "   ✅ Done"
fi

# Install to Claude
if [ -d "$HOME/.claude" ]; then
    echo "📦 Installing to Claude Code..."
    mkdir -p "$CLAUDE_DIR"
    
    for skill_dir in "$SKILLS_DIR"/*/; do
        skill_name=$(basename "$skill_dir")
        
        # Copy SKILL.md and remove metadata.hermes section
        python3 -c "
import re

with open('$skill_dir/SKILL.md', 'r') as f:
    content = f.read()

# Remove metadata.hermes section
content = re.sub(
    r'(metadata:\n  hermes:\n    tags: \[.*?\]\n    related_skills: \[.*?\]\n)',
    '',
    content
)

with open('$CLAUDE_DIR/$skill_name.md', 'w') as f:
    f.write(content)
"
    done
    
    INSTALLED+=("Claude")
    echo "   ✅ Done"
fi

echo ""
echo "========================================"
echo "✅ Installation complete!"
echo ""

if [ ${#INSTALLED[@]} -eq 0 ]; then
    echo "⚠️  No platforms detected. Skills available in:"
    echo "   $SKILLS_DIR"
else
    echo "📋 Installed to:"
    for platform in "${INSTALLED[@]}"; do
        echo "   • $platform"
    done
fi

echo ""
echo "📚 Available skills:"
ls -1 "$SKILLS_DIR" | sed 's/^/   • /'

echo ""
echo "🔧 Usage:"
echo "   Hermes/OpenCode: skill_view(name='pd')"
echo "   Claude: /pd"
