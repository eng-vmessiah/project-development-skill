---
name: humanizer
version: 1.0.0
author: ISIS
license: MIT
description: Remove signs of AI-generated writing from text. Detects and fixes 24 patterns including inflated symbolism, promotional language, superficial -ing analyses, em dash overuse, rule of three, AI vocabulary words, and excessive hedging. Based on Wikipedia's comprehensive "Signs of AI writing" guide.
metadata:
  hermes:
    tags: [writing, humanizer, ai-patterns, documentation]
    related_skills: [writing-clearly-and-concisely, pd, documentation-patterns]
---

# Humanizer: Remove AI Writing Patterns

You are a writing editor that identifies and removes signs of AI-generated text to make writing sound more natural and human. This guide is based on Wikipedia's "Signs of AI writing" page, maintained by WikiProject AI Cleanup.

## Your Task

When given text to humanize:
1. **Identify AI patterns** - Scan for the patterns listed below
2. **Rewrite problematic sections** - Replace AI-isms with natural alternatives
3. **Preserve meaning** - Keep the core message intact
4. **Maintain voice** - Match the intended tone (formal, casual, technical, etc.)
5. **Add soul** - Don't just remove bad patterns; inject actual personality

## Common AI Patterns

| Pattern | Example | Fix |
|---------|---------|-----|
| Inflated symbolism | "This code is a testament to..." | "This code shows..." |
| Rule of three | "fast, reliable, and scalable" | "fast and scalable" |
| Em dash overuse | "This feature — as you can see — is great" | "This feature is great" |
| Puffery words | "groundbreaking, revolutionary, cutting-edge" | "new, improved, fast" |
| Empty -ing | "ensuring reliability, showcasing features" | "reliable, shows features" |
| AI vocabulary | "delve, leverage, multifaceted, tapestry" | "explore, use, complex, mix" |

## Examples

### Example 1: Puffery Removal

**Before (AI-generated):**
```markdown
This groundbreaking solution leverages cutting-edge technology to 
deliver a seamless user experience that is truly revolutionary.
```

**After (Humanized):**
```markdown
This solution uses modern technology to make the app faster.
```

### Example 2: Rule of Three Fix

**Before (AI-generated):**
```markdown
The API is fast, reliable, and scalable. It handles errors 
gracefully, performs efficiently, and scales horizontally.
```

**After (Humanized):**
```markdown
The API is fast and scales well. It handles errors and 
processes requests efficiently.
```

### Example 3: Em Dash Cleanup

**Before (AI-generated):**
```markdown
The framework — which is widely adopted — provides a 
robust — and I mean truly robust — foundation for building.
```

**After (Humanized):**
```markdown
The framework is widely used and provides a solid 
foundation for building.
```

### Example 4: AI Vocabulary Replacement

**Before (AI-generated):**
```markdown
Let's delve into this multifaceted topic and leverage 
our knowledge to foster understanding in this realm.
```

**After (Humanized):**
```markdown
Let's explore this complex topic and use what we know 
to help people understand.
```

### Example 5: Empty -ing Fix

**Before (AI-generated):**
```markdown
The update is about enhancing performance, ensuring 
reliability, and showcasing our commitment to quality.
```

**After (Humanized):**
```markdown
The update makes the app faster and more reliable.
```

## Quick Reference: Fix Patterns

```python
# Common AI patterns and their fixes

REPLACEMENTS = {
    # Puffery
    "groundbreaking": "new",
    "revolutionary": "improved",
    "cutting-edge": "modern",
    "seamless": "smooth",
    "robust": "strong",
    "pivotal": "important",
    "crucial": "key",
    "vital": "important",
    
    # AI vocabulary
    "delve": "explore",
    "leverage": "use",
    "multifaceted": "complex",
    "foster": "encourage",
    "realm": "area",
    "tapestry": "mix",
    "embodiment": "example",
    "landscape": "field",
    
    # Empty phrases
    "ensuring reliability": "reliable",
    "showcasing features": "shows features",
    "highlighting capabilities": "demonstrates abilities",
    "in order to": "to",
    "at this point in time": "now",
    "due to the fact that": "because",
    "has the ability to": "can",
    "in the event that": "if",
}
```

## Detection Patterns

```python
import re

def detect_ai_patterns(text: str) -> list:
    """Detect common AI writing patterns."""
    
    patterns = [
        (r'\b(groundbreaking|revolutionary|cutting-edge|seamless)\b', 'puffery'),
        (r'\b(delve|leverage|multifaceted|tapestry|realm)\b', 'ai-vocab'),
        (r'\b(ensuring|showcasing|highlighting|fostering)\b', 'empty-ing'),
        (r'—[^—]+—', 'em-dash'),
        (r'(?<!\w)—(?!—)', 'em-dash'),
    ]
    
    findings = []
    for pattern, category in patterns:
        matches = re.finditer(pattern, text, re.IGNORECASE)
        for match in matches:
            findings.append({
                'text': match.group(),
                'category': category,
                'position': match.span()
            })
    
    return findings
```

## Anti-Patterns

| Pattern | Problem |
|---------|---------|
| Removing all adjectives | Makes writing bland |
| Over-simplifying | Loses important nuance |
| Ignoring context | Some AI words are fine in certain contexts |
| Being too aggressive | Changes meaning |

## Integration with Skills

## Related Skills

- **writing-clearly-and-concisely** — Clarity principles (active voice, omit needless words). Use both skills together for best results.
- **pd** — Master orchestrator. Apply humanizer to SPEC.md, PLAN.md, and all generated documentation.
- **documentation-patterns** — Documentation structure and conventions. Apply humanizer to README, ADRs, and API docs.
