# Testing Priority-Chain Functions

A common testing pitfall: functions that use `if-elif` chains with overlapping conditions. The first matching condition wins, which can silently mask your test's intended target.

## The Pattern

```python
def detect_type(text: str) -> str:
    word_count = len(text.split())

    is_narration = word_count >= 30
    is_short = word_count <= 8
    is_question = '?' in text

    if is_narration:
        return 'narration'
    elif is_short:
        return 'short'
    elif is_question:
        return 'question'
    else:
        return 'normal'
```

Here, **priority order** is: narration > short > question > normal.

A prompt like `"Como fazer isso?"` (3 words) hits `short` (≤8 words) BEFORE `question` — even though it has a `?`.

## Root Cause

You test the **narrowest condition** with a prompt that also satisfies a **broader higher-priority condition**. The if-elif executes the first match, so your test assertion never runs.

## Debugging Checklist

When a classification test fails unexpectedly:

1. **List ALL conditions** in the function's if-elif chain, in order
2. **For each condition**, ask: "Does my test prompt satisfy THIS condition?"
3. **If yes** and it's higher-priority than your target: your prompt is too broad
4. **Fix** by making the prompt satisfy ONLY the target condition

## Fixing Strategies

### Strategy 1: Add more words

If `short` (≤8 words) masks `question`:

```python
# BROKEN — 3 words, hits 'short' before 'question'
ctx = detect_type("Como fazer isso?")

# FIXED — 10 words, skips 'short'
ctx = detect_type("Você pode me explicar como funciona esse sistema?")
```

### Strategy 2: Remove higher-priority keywords

If `instruction` keywords mask `question`:

```python
# BROKEN — "como fazer" matches instruction keywords
ctx = detect_type("Como fazer isso?")

# FIXED — no instruction keywords, has ?
ctx = detect_type("Você pode me explicar isso?")
```

### Strategy 3: Add emotional markers + more words

If `short` masks `emotional`:

```python
# BROKEN — 3 words, hits 'short'
ctx = detect_type("kkkk que demais!")

# FIXED — 10 words, has emotional markers
ctx = detect_type("kkkk cara isso foi muito engraçado mano que demais!")
```

### Strategy 4: Write the priority test first

Instead of testing individual conditions, test the full priority order:

```python
def test_priority_narration_over_question(self):
    """Narration (30+ words) takes priority over question."""
    prompt = "very long text " * 30 + "?"
    assert detect_type(prompt) == "narration"

def test_priority_short_over_emotional(self):
    """Short (≤8 words) takes priority over emotional markers."""
    prompt = "kkkk lol"
    assert detect_type(prompt) == "short"

def test_priority_emotional_over_question(self):
    """Emotional markers in medium-length text take priority over question."""
    prompt = "kkkk cara isso foi muito engraçado?"
    assert detect_type(prompt) == "emotional"
```

Now the priority chain is explicit in your tests, and you don't accidentally mask conditions.

## Real Example: TTS Content Detection

From `bridge/app/api/tts_preprocess.py` — `_detect_content_type()` has this priority:

```
instruction (has step keywords)     → quality=10, speed=0.92
narration      (≥30 words)          → quality=12, speed=0.95
short answer   (≤8 words)           → quality=7,  speed=1.05
emotional      (has !/kkkk/mano)    → quality=9,  speed=1.02
question       (has ? or starts with como/qual/onde) → quality=8, speed=0.98
normal         (no match)           → quality=8,  speed=1.0
```

When testing each type, verify your prompt:
- Has **enough words** to escape `short` (unless you're testing short)
- Has **no instruction keywords** like "passo" or "como fazer" (unless testing instruction)
- Has the **target feature** (?, kkkk, !, etc.)

`word_count = len(text.split())` — count words carefully.
