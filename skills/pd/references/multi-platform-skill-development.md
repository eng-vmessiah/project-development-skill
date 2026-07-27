# Multi-Platform Skill Development

Workflow for creating, validating, and distributing skills across Hermes Agent, OpenCode, and Claude Code.

## Platform Formats

| Platform | Location | Format |
|----------|----------|--------|
| Hermes | `~/.hermes/skills/<category>/<skill>/SKILL.md` | Frontmatter + `metadata.hermes` |
| OpenCode | `~/.config/opencode/skills/<skill>/SKILL.md` | Frontmatter (no metadata.hermes) |
| Claude | `~/.claude/commands/<skill>.md` | Frontmatter (no metadata.hermes) |

## Sync Script Pattern

```bash
#!/bin/bash
# Sync skills to all platforms

SKILLS_DIR="skills"
HERMES_DIR="$HOME/.hermes/skills/software-development"
OPENCODE_DIR="$HOME/.config/opencode/skills"
CLAUDE_DIR="$HOME/.claude/commands"

for skill_dir in "$SKILLS_DIR"/*/; do
    skill_name=$(basename "$skill_dir")

    # Hermes (full copy with templates)
    mkdir -p "$HERMES_DIR/$skill_name"
    cp -r "$skill_dir"* "$HERMES_DIR/$skill_name/"

    # OpenCode (remove metadata.hermes)
    mkdir -p "$OPENCODE_DIR/$skill_name"
    python3 -c "
import re
with open('$skill_dir/SKILL.md', 'r') as f:
    content = f.read()
content = re.sub(r'(metadata:\n  hermes:\n    tags: \[.*?\]\n    related_skills: \[.*?\]\n)', '', content)
with open('$OPENCODE_DIR/$skill_name/SKILL.md', 'w') as f:
    f.write(content)
"

    # Claude (flat structure, .md extension)
    cp "$skill_dir/SKILL.md" "$CLAUDE_DIR/$skill_name.md"
done
```

## Analyzing External Repos

Workflow for synthesizing skills from external sources:

1. **Fetch repo info**: `curl -s https://api.github.com/repos/{owner}/{repo}`
2. **Read README**: Understand purpose and patterns
3. **Identify patterns**: What problems does it solve?
4. **Check license**: MIT, Apache, etc. (required for attribution)
5. **Synthesize skill**: Rewrite in own words, don't copy
6. **Add attribution**: Credit original in README or skill references

## Attribution Requirements

| License | Requirement |
|---------|-------------|
| MIT | Include copyright notice |
| Apache 2.0 | Include license file |
| No license | Cannot use (all rights reserved) |
| Public domain | No attribution required |

For skills derived from external sources:
- Rewrite content in own words
- Add attribution in skill references or README
- Don't copy code verbatim
- Focus on patterns, not implementation

## Validation Script

```bash
#!/bin/bash
# Validate all skills

for skill in skills/*/SKILL.md; do
    # Check frontmatter
    # Check size (max 35k)
    # Check required fields
    # Check for code examples
done
```

## Skill Size Guidelines

| Size | Category | Action |
|------|----------|--------|
| <5k | Small | Consider merging |
| 5-15k | Ideal | Perfect |
| 15-20k | Large | Consider splitting |
| >20k | Too large | Must split |

## Cross-Reference Pattern

When creating new skills, update related skills' frontmatter:

```yaml
# In new skill
metadata:
  hermes:
    related_skills: [existing-skill-1, existing-skill-2]

# In existing skill (send PR)
metadata:
  hermes:
    related_skills: [..., new-skill, ...]
```

## Repository Structure

```
project-name/
├── README.md
├── CONTRIBUTING.md
├── CHANGELOG.md
├── LICENSE
├── install.sh
├── scripts/
│   └── validate.sh
├── docs/
│   ├── ARCHITECTURE.md
│   └── CREATING-SKILLS.md
├── examples/
│   └── <example>/
└── skills/
    └── <skill-name>/
        ├── SKILL.md
        └── templates/ (optional)
```

## Common Pitfalls

1. **Forgetting metadata.hermes** — OpenCode/Claude don't use it
2. **Not testing all platforms** — Each has quirks
3. **Missing attribution** — License violation risk
4. **Copying verbatim** — Rewrite in own words
5. **No validation** — Broken skills in production
