# Creating Skills

A comprehensive guide to creating new skills for the Project Development ecosystem.

## What is a Skill?

A skill is a reusable knowledge module that teaches an AI agent how to perform a specific task. Skills contain:

1. **Metadata** — Name, description, version, tags
2. **When to use** — Trigger conditions
3. **Core content** — The actual knowledge
4. **Examples** — Code and usage examples
5. **Anti-patterns** — What NOT to do
6. **References** — Links to related skills

## Skill Anatomy

```markdown
---
name: skill-name
description: "One sentence description starting with a verb."
version: 1.0.0
author: Your Name
license: MIT
metadata:
  hermes:
    tags: [tag1, tag2, tag3]
    related_skills: [skill-a, skill-b]
---

# Skill Name

## When to Use

- Use when [condition]
- Use when [condition]

## Overview

Brief explanation of the skill.

## Core Content

### Section 1

Detailed content...

```python
# Code example
```

### Section 2

More content...

## Anti-Patterns

| Pattern | Problem |
|---------|---------|
| Bad practice | Why it's bad |

## Integration

### related-skill
How this skill connects to related-skill.

## References

- Source 1
- Source 2
```

## Step-by-Step Guide

### Step 1: Choose a Name

Rules:
- Lowercase
- Hyphens for spaces (not underscores)
- Max 64 characters
- Descriptive and unique

Good:
```
api-design-patterns
react-testing
docker-deployment
```

Bad:
```
patterns (too vague)
my-skill (not descriptive)
API_Design_Patterns (wrong format)
```

### Step 2: Write the Description

Rules:
- One sentence
- Starts with a verb
- Describes what the skill does
- Ends with period

Good:
```
description: "Implement JWT authentication with refresh tokens."
description: "Debug Python applications using debugpy."
description: "Write maintainable React components with hooks."
```

Bad:
```
description: "Auth stuff" (too vague)
description: "This skill helps with..." (not action-oriented)
description: "JWT" (incomplete)
```

### Step 3: Add Metadata

```yaml
metadata:
  hermes:
    tags: [jwt, authentication, security, api]
    related_skills: [auth-patterns, clean-code]
```

Tags:
- 3-8 tags
- Lowercase
- Relevant to content
- No duplicates

Related skills:
- Bidirectional (both skills reference each other)
- Only include truly related skills
- Max 10 related skills

### Step 4: Write When to Use

Be specific about trigger conditions:

```markdown
## When to Use

- Starting a new project
- Adding authentication to an API
- Implementing user management
- When you need role-based access control
```

### Step 5: Write Core Content

Structure:
1. Overview (what and why)
2. Core concepts
3. Implementation details
4. Code examples
5. Anti-patterns

Tips:
- Use headers (##, ###)
- Include code examples
- Show both "do" and "don't"
- Keep sections focused

### Step 6: Add Code Examples

Rules:
- Language tag (```python, ```typescript, etc.)
- Complete and runnable
- Comments explain key points
- Max 50 lines per example

### Step 7: Add Anti-Patterns

```markdown
## Anti-Patterns

| Pattern | Problem |
|---------|---------|
| Storing JWT in localStorage | XSS vulnerability |
| Long-lived tokens | Increased attack window |
| No rate limiting | Brute force attacks |
```

### Step 8: Add Cross-References

Update both your skill and related skills:

```yaml
# In your skill
metadata:
  hermes:
    related_skills: [clean-code, pd]

# In clean-code's frontmatter (send PR)
metadata:
  hermes:
    related_skills: [..., your-skill, ...]
```

## Quality Standards

### Size

| Size | Category | Action |
|------|----------|--------|
| <5k | Small | Consider merging |
| 5-15k | Ideal | Perfect |
| 15-20k | Large | Consider splitting |
| >20k | Too large | Must split |

### Completeness

- [ ] Frontmatter complete
- [ ] Description clear
- [ ] When to use section
- [ ] Overview section
- [ ] At least 3 code examples
- [ ] Anti-patterns section
- [ ] Cross-references
- [ ] References section

### Testing

Before submitting:

1. Install locally: `./install.sh`
2. Test in Hermes: `skill_view(name='your-skill')`
3. Test in OpenCode: `skill_view(name='your-skill')`
4. Test in Claude: `/your-skill`

## Common Patterns

### Pattern: Decision Tree

```markdown
## Which Approach?

| Requirement | Approach |
|-------------|----------|
| Simple case | Option A |
| Complex case | Option B |
| Performance critical | Option C |
```

### Pattern: Code + Explanation

```markdown
## Implementation

Here's how to implement this:

```python
# Code here
```

**Why this works:**
- Reason 1
- Reason 2
- Reason 3
```

### Pattern: Do / Don't

```markdown
## Best Practices

**Do:**
```python
# Good example
```

**Don't:**
```python
# Bad example
```
```

## Submitting Your Skill

1. Fork the repository
2. Create branch: `git checkout -b feat/your-skill`
3. Add skill: `skills/your-skill/SKILL.md`
4. Update related skills' frontmatter
5. Test with `./install.sh`
6. Submit PR with description

## Getting Help

- Open an issue with label `question`
- Check existing skills for examples
- Read CONTRIBUTING.md
