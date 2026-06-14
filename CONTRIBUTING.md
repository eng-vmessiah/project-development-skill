# Contributing to Project Development Skills

Thank you for your interest in contributing! This document explains how to add new skills or improve existing ones.

## Quick Start

1. Fork the repository
2. Create a feature branch: `git checkout -b feat/my-skill`
3. Add your skill
4. Test with `./install.sh`
5. Submit a pull request

## Adding a New Skill

### 1. Create the Directory

```bash
mkdir -p skills/my-skill
```

### 2. Create SKILL.md

Use this template:

```markdown
---
name: my-skill
description: "Short description of what this skill does."
version: 1.0.0
author: Your Name
license: MIT
metadata:
  hermes:
    tags: [relevant, tags, here]
    related_skills: [other-skills-this-connects-to]
---

# My Skill

## When to Use

- Scenario 1
- Scenario 2

## Overview

Brief explanation of the skill's purpose and approach.

## Core Content

### Section 1

Detailed content with examples.

```python
# Code example
def example():
    pass
```

### Section 2

More content...

## Anti-Patterns

| Pattern | Problem |
|---------|---------|
| Bad practice | Why it's bad |

## Integration with Other Skills

### skill-name
How this skill connects to skill-name.

## References

- Source 1
- Source 2
```

### 3. Quality Checklist

Before submitting, verify:

- [ ] **Frontmatter complete** — name, description, version, author, license, metadata
- [ ] **Description clear** — One sentence, starts with verb
- [ ] **Tags relevant** — 3-8 lowercase tags
- [ ] **Cross-references** — Related skills listed in metadata
- [ ] **Examples work** — Code examples are valid
- [ ] **No duplication** — Doesn't repeat existing skills
- [ ] **Size reasonable** — Under 20k chars (ideal: 8-15k)
- [ ] **English only** — All content in English

### 4. Cross-References

Add bidirectional references:

```yaml
# In your skill's frontmatter
metadata:
  hermes:
    related_skills: [clean-code, pd, systematic-debugging]

# In related skills' frontmatter (send PR to update)
metadata:
  hermes:
    related_skills: [..., my-skill, ...]
```

## Improving Existing Skills

### Small Fixes (Typos, Examples)

1. Edit directly in `skills/<name>/SKILL.md`
2. Submit PR with title: `fix: correct typo in <skill-name>`

### Content Changes

1. Open an issue first to discuss
2. Get approval from maintainers
3. Submit PR with clear description

### Adding Cross-References

1. Update both skills' `related_skills` in frontmatter
2. Add integration section if needed

## Skill Categories

| Category | Skills | Purpose |
|----------|--------|---------|
| **Core** | pd, clean-code, ddd-development | Foundation patterns |
| **Quality** | test-driven-development, requesting-code-review, systematic-debugging | Code quality |
| **Patterns** | design-patterns, auth-patterns, service-composition | Design patterns |
| **AI** | ai-optimization, ai-regression-testing | AI-specific |
| **Writing** | humanizer, writing-clearly-and-concisely, writing-plans | Communication |

## Style Guide

### Code Examples

- Use Python as primary language
- Include TypeScript when relevant
- Add comments explaining key points
- Keep examples short (< 50 lines)

### Formatting

- Use headers (##, ###) consistently
- Tables for comparisons
- Code blocks with language tags
- Bullet points for lists

### Tone

- Direct and practical
- No unnecessary words
- Action-oriented ("Use X when...")
- Include both "do" and "don't"

## Testing Your Skill

```bash
# 1. Install locally
./install.sh

# 2. Test in Hermes
skill_view(name='my-skill')

# 3. Test in OpenCode
skill_view(name='my-skill')

# 4. Test in Claude
/my-skill
```

## Pull Request Template

```markdown
## What

Brief description of changes.

## Why

Why this change is needed.

## How

How you tested the changes.

## Checklist

- [ ] Frontmatter complete
- [ ] Cross-references updated
- [ ] Examples tested
- [ ] Size under 20k chars
```

## Code of Conduct

- Be respectful
- Focus on quality
- Help others learn
- Accept feedback gracefully

## Questions?

Open an issue with the label `question`.
