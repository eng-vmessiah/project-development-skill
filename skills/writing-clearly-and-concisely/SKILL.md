---
name: writing-clearly-and-concisely
version: 1.0.0
author: ISIS
license: MIT
description: Write clear, forceful prose for humans. Based on Strunk's Elements of Style. Use for documentation, commit messages, error messages, reports, UI text, or any writing a human will read. Covers active voice, omitting needless words, concrete language, and AI writing patterns to avoid.
metadata:
  hermes:
    tags: [writing, documentation, style, clarity]
    related_skills: [clean-code, humanizer, pd]
---

# Writing Clearly and Concisely

## Overview

Write with clarity and force. Based on William Strunk Jr.'s _The Elements of Style_ (1918).

## When to Use

- Documentation, README files, technical explanations
- Commit messages, pull request descriptions
- Error messages, UI copy, help text, comments
- Reports, summaries, or any explanation
- Editing to improve clarity

**If you're writing sentences for a human to read, use this skill.**

## Core Rules

### Active Voice
- "The committee decided" not "It was decided by the committee"
- "The app crashed" not "An error was encountered"
- Active is shorter, clearer, more forceful

### Omit Needless Words
- "Because" not "due to the fact that"
- "Now" not "at this point in time"
- "Can" not "has the ability to"
- "If" not "in the event that"
- "About" not "with regard to"

Every word that adds nothing is a word wasted.

### Concrete Language
- "3 million lines of code" not "a substantial amount of code"
- "Takes 200ms" not "highly performant"
- "Opens in 3 seconds" not "seamless user experience"

Prefer definite, specific, concrete language. Details are convincing.

### Positive Form
- "Bad" not "not good"
- "Forget" not "fail to remember"
- "Ignore" not "pay no attention to"
- "Honest" not "not dishonest"

State what IS, not what ISN'T.

### One Paragraph Per Topic
- Begin each paragraph with a topic sentence
- Each paragraph = one idea
- Transition between paragraphs logically

### Keep Related Words Together
- "He noticed a large stain in the rug" not "He noticed a stain in the rug that was large"
- Keep modifiers close to what they modify

### Place Emphatic Words at End
- "This duty we must fulfill" not "We must fulfill this duty"
- End with what matters most

## AI Patterns to Avoid

- **Puffery:** pivotal, crucial, vital, testament, enduring legacy
- **Empty "-ing" phrases:** ensuring reliability, showcasing features, highlighting capabilities
- **Promotional adjectives:** groundbreaking, seamless, robust, cutting-edge
- **Overused AI vocabulary:** delve, leverage, multifaceted, foster, realm, tapestry
- **Formatting overuse:** excessive bullets, emoji decorations, bold on every other word

Be specific, not grandiose. Say what it actually does.

## Quick Reference

| Say this | Not this |
|----------|----------|
| can | has the ability to |
| now | at this point in time |
| because | due to the fact that |
| if | in the event that |
| about | with regard to |
| before | prior to |
| after | subsequent to |
| is | is able to be |
| must | is required to |
| uses | makes use of |

## Examples

### Example 1: Active Voice

**Before (Passive):**
```markdown
The configuration file is loaded by the application. 
Errors are logged to the console. Dependencies are 
installed automatically.
```

**After (Active):**
```markdown
The application loads the configuration file. It logs 
errors to the console and installs dependencies.
```

### Example 2: Omit Needless Words

**Before (Wordy):**
```markdown
In order to make use of this feature, you will need to 
have the ability to configure the settings in such a 
way that they are appropriate for your use case.
```

**After (Concise):**
```markdown
To use this feature, configure the settings for your case.
```

### Example 3: Concrete Language

**Before (Vague):**
```markdown
The system provides high performance and handles a 
substantial amount of requests efficiently.
```

**After (Specific):**
```markdown
The system processes 10,000 requests per second with 
under 50ms latency.
```

### Example 4: Positive Form

**Before (Negative):**
```markdown
If you do not remember your password, you will not be 
able to log in to the application.
```

**After (Positive):**
```markdown
Forgot your password? Reset it to log in.
```

### Example 5: Complete Rewrite

**Before (AI-style):**
```markdown
This groundbreaking update leverages cutting-edge 
technology to deliver a seamless user experience. 
We are confident that this revolutionary feature will 
enhance your workflow and foster greater productivity.
```

**After (Clear):**
```markdown
This update adds a search feature. It helps you find 
files faster.
```

## Code Examples

### Spell-Checker for Wordiness

```python
import re

WORDY_PHRASES = {
    "in order to": "to",
    "due to the fact that": "because",
    "at this point in time": "now",
    "has the ability to": "can",
    "in the event that": "if",
    "with regard to": "about",
    "prior to": "before",
    "subsequent to": "after",
    "is able to be": "can be",
    "is required to": "must",
    "makes use of": "uses",
    "a large number of": "many",
    "a sufficient amount of": "enough",
    "at the present time": "now",
    "for the purpose of": "to",
    "in the near future": "soon",
}

def fix_wordiness(text: str) -> str:
    """Replace wordy phrases with concise alternatives."""
    fixed = text
    for wordy, concise in WORDY_PHRASES.items():
        fixed = re.sub(
            re.escape(wordy), 
            concise, 
            fixed, 
            flags=re.IGNORECASE
        )
    return fixed
```

### Active Voice Detector

```python
import re

PASSIVE_INDICATORS = [
    r"\b(is|are|was|were|be|been|being)\s+(VERB)ed\b",
    r"\b(is|are|was|were|be|been|being)\s+(VERB)en\b",
]

def detect_passive(text: str) -> list:
    """Detect passive voice constructions."""
    # Simple heuristic - not 100% accurate
    passive_patterns = [
        r"\b(is|are|was|were)\s+\w+ed\s+by\b",
        r"\b(has|have|had)\s+been\s+\w+ed\b",
    ]
    
    findings = []
    for pattern in passive_patterns:
        matches = re.finditer(pattern, text, re.IGNORECASE)
        for match in matches:
            findings.append({
                'text': match.group(),
                'position': match.span(),
                'suggestion': 'Consider using active voice'
            })
    
    return findings
```

## Anti-Patterns

| Pattern | Problem |
|---------|---------|
| Over-simplifying | Loses important nuance |
| Removing all adjectives | Makes writing bland |
| Ignoring audience | Technical vs. non-technical |
| Being too terse | Unclear or confusing |

## Integration with Skills

### humanizer
- Use both skills together for best results
- humanizer focuses on AI-isms
- This skill focuses on clarity principles

### clean-code
- Apply to code comments
- Apply to documentation
- Apply to commit messages

### pd
- Use when writing SPEC.md, PLAN.md
- Use when reviewing documentation
- Use for commit messages
