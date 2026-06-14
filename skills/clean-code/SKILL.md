---
name: clean-code
description: "Use when writing, reviewing, or refactoring code for readability and maintainability. Covers naming, functions, comments, error handling, classes, testing, and common code smells with concrete rules and anti-patterns."
version: 1.0.0
author: ISIS
license: MIT
metadata:
  hermes:
    tags: [clean-code, refactoring, naming, testing, code-quality, craftsmanship]
    related_skills: [ddd-development, karpathy-guidelines, pd, requesting-code-review, systematic-debugging, test-driven-development]
---

# Clean Code

## Overview

Clean Code is code that has been **taken care of**. Someone has taken the time to keep it simple and orderly. They have paid appropriate attention to details. They have cared.

**Beck's Rules of Simple Code** (priority order):
1. Runs all the tests
2. Contains no duplication
3. Expresses all the design ideas in the system
4. Minimizes the number of entities (classes, methods, functions)

**Source:** Robert C. Martin — *Clean Code: A Handbook of Agile Software Craftsmanship* (2008)

## When to Use

- Writing new code (functions, classes, modules)
- Refactoring existing code for readability
- Code review — checking for quality issues
- Debugging — tracing logic through clean abstractions

**Don't use for:**
- Prototypes/throwaway code (clean later, not now)
- Performance-critical hot paths (optimize first, clean after)

---

## I. Meaningful Names

### Rules

| # | Rule | Bad | Good |
|---|------|-----|------|
| 1 | **Use intention-revealing names** | `d` | `elapsedTimeInDays` |
| 2 | **Avoid disinformation** | `accountList` (when it's not a List) | `accounts` |
| 3 | **Make meaningful distinctions** | `a1`, `a2` | `source`, `destination` |
| 4 | **Use pronounceable names** | `genymdhms` | `generationTimestamp` |
| 5 | **Use searchable names** | `7` (magic number) | `MAX_CLASSES_PER_STUDENT` |
| 6 | **Avoid encodings** | `m_dsc` (Hungarian) | `description` |
| 7 | **Avoid mental mapping** | `tmp` for anything long-lived | Use descriptive name |
| 8 | **Pick one word per concept** | `fetch`, `retrieve`, `get` (mixed) | Pick one, use consistently |
| 9 | **Don't pun** | `add()` for concatenation and addition | `append()`, `sum()` |
| 10 | **Use solution domain names** | `parser` | `Parser` (pattern name) |
| 11 | **Use problem domain names** | `engine` | `RiskCalculator` |
| 12 | **Add meaningful context** | `state` | `orderState`, `shippingState` |
| 13 | **Don't add gratuitous context** | `address` → `streetAddress` | `address` (context obvious) |

### Naming Decision Tree

```
Is it a concept from the business domain?
  → YES → Use the problem domain name (e.g., RiskCalculator)
  → NO ↓

Is it a known pattern/algorithm?
  → YES → Use the solution domain name (e.g., Adapter, Factory)
  → NO ↓

Does it need context to be understood?
  → YES → Add prefix/suffix (e.g., orderState, not state)
  → NO → Use the simplest descriptive name
```

---

## II. Functions

### The Three Rules

1. **Small!** — Functions should be very small (ideal: 3-5 lines, max: 20)
2. **Do One Thing** — A function should do ONE thing, do it well, do it only
3. **One Level of Abstraction** — Each function should operate at ONE level of abstraction

### Function Structure

```python
# BAD: Multiple levels of abstraction mixed
def process_order(order):
    # High-level logic
    if order.is_valid():
        # Low-level detail
        for item in order.items:
            if item.quantity > 0:
                db.execute("INSERT INTO...")
                send_email(order.customer)
        # Back to high-level
        order.status = "processed"

# GOOD: Each level is clear
def process_order(order):
    validate_order(order)
    persist_order_items(order)
    notify_customer(order)
    mark_order_processed(order)

def validate_order(order):
    if not order.is_valid():
        raise InvalidOrderError(order)

def persist_order_items(order):
    for item in order.items:
        repository.save(item)

def notify_customer(order):
    email_service.send(order.customer, order_confirmation_template(order))

def mark_order_processed(order):
    order.status = "processed"
```

### Function Rules

| Rule | What It Means |
|------|--------------|
| **Small** | Ideal 3-5 lines, never > 20 |
| **Do One Thing** | If you can extract another function from it, it does more than one thing |
| **One Level of Abstraction** | No mixing high-level orchestration with low-level details |
| **Stepdown Rule** | Caller should be above callees (top-to-bottom reading) |
| **Few Arguments** | 0 (ideal), 1-2 (ok), 3+ (refactor to object) |
| **No Side Effects** | Don't mutate hidden state; return values instead |
| **No Output Args** | Don't pass objects to be modified; return new objects |
| **Command-Query Separation** | Functions should either do something OR answer something, not both |

### Argument Rules

```python
# BAD: Flag argument (does two things)
def generate_report(order, include_header):
    ...

# GOOD: Two functions
def generate_report(order):
    ...

def generate_report_with_header(order):
    ...
```

```python
# BAD: Dyadic (two args) — hard to remember order
def create_user(name, email)

# GOOD: Argument object
def create_user(UserRegistration registration)
```

---

## III. Comments

### The Golden Rule

> "Don't comment bad code — rewrite it." — Brian W. Kernighan

### Good Comments

| Type | When to Use | Example |
|------|-------------|---------|
| **Legal** | Copyright, licenses | `// MIT License` |
| **Informative** | Explain meaning of obscure return | `// returns the regex match` |
| **Intent** | Explain WHY, not what | `// sort to optimize subsequent binary search` |
| **Clarification** | Non-obvious parameter meaning | `// timeout in milliseconds` |
| **Warning** | Consequences of not doing something | `// Don't delete — needed for backward compat` |
| **TODO** | Planned work (must have owner) | `// TODO(Vitor): migrate to new API` |
| **Amplification** | Emphasize importance | `// VERY important — don't remove` |

### Bad Comments

| Type | Why It's Bad | Fix |
|------|-------------|-----|
| **Mumbling** | Vague, adds noise | Remove or clarify |
| **Redundant** | Says what code already says | Remove |
| **Misleading** | Wrong information | Fix or remove |
| **Mandated** | "Required by process" | Fight the process |
| **Journal** | "Changed on 2024-01-15" | Use git |
| **Noise** | `// get the value` on `value = x` | Remove |
| **Commented-out code** | Dead code with excuses | Delete (git has history) |
| **Function headers** | Javadoc on private methods | Name the method better |

---

## IV. Error Handling

### Rules

| # | Rule | Why |
|---|------|-----|
| 1 | **Use exceptions, not return codes** | Return codes clutter the caller |
| 2 | **Write try-catch-finally first** | Forces you to think about error paths |
| 3 | **Use unchecked exceptions** | Checked exceptions couple callers to implementation |
| 4 | **Provide context with exceptions** | "Couldn't load order 123" not "Error loading" |
| 5 | **Define exception classes by caller's needs** | What can the caller DO about it? |
| 6 | **Define the normal flow** | Exceptional cases are... exceptional |
| 7 | **Don't return null** | Creates null checks everywhere; return empty collections or Null Object |
| 8 | **Don't pass null** | Avoid NullPointerExceptions at the source |

```python
# BAD: Error codes clutter logic
def get_order(order_id):
    result = repository.find(order_id)
    if result is None:
        return None  # Caller must check!
    return result

# GOOD: Exceptions separate error handling from logic
def get_order(order_id):
    order = repository.find(order_id)
    if order is None:
        raise OrderNotFoundError(order_id)
    return order
```

```python
# BAD: Returning null everywhere
def calculate_discount(customer_id):
    customer = get_customer(customer_id)
    if customer is None:
        return None  # Null propagates!
    return customer.discount_rate()

# GOOD: Fail fast, or use Null Object
def calculate_discount(customer_id):
    customer = get_customer(customer_id)  # raises if not found
    return customer.discount_rate()
```

---

## V. Unit Tests

### Three Laws of TDD

1. **You may not write production code until you have written a failing unit test**
2. **You may not write more of a unit test than is sufficient to fail** (not compiling counts as failing)
3. **You may not write more production code than is sufficient to pass** the currently failing test

### F.I.R.S.T. Principles

| Letter | Principle | What It Means |
|--------|-----------|---------------|
| **F** | Fast | Tests run in milliseconds |
| **I** | Independent | Tests don't depend on each other |
| **R** | Repeatable | Same result every time, any environment |
| **S** | Self-Validating | Pass/fail, no manual inspection |
| **T** | Timely | Written at the right time (just before production code) |

### Clean Test Rules

| Rule | What It Means |
|------|--------------|
| **One Assert per Test** | Each test tests ONE concept |
| **Single Concept per Test** | Name says what ONE thing is tested |
| **Domain-Specific Language** | Tests read like domain statements, not implementation |

```python
# BAD: Multiple asserts, unclear concept
def test_order():
    order = create_order()
    assert order.status == "pending"
    assert order.items_count == 0
    assert order.total == 0

# GOOD: Single concept, domain language
def test_new_order_has_pending_status():
    order = Order.create()
    assert order.is_pending()

def test_new_order_starts_empty():
    order = Order.create()
    assert order.is_empty()
```

---

## VI. Classes

### The Single Responsibility Principle (SRP)

> A class should have only one reason to change.

```python
# BAD: Class does too many things
class Report:
    def generate(self): ...
    def format_as_pdf(self): ...
    def save_to_database(self): ...
    def send_email(self): ...

# GOOD: Each class has one responsibility
class ReportGenerator:
    def generate(self, data): ...

class ReportFormatter:
    def to_pdf(self, report): ...

class ReportRepository:
    def save(self, report): ...

class ReportNotifier:
    def send(self, report, recipient): ...
```

### Class Rules

| Rule | Target |
|------|--------|
| **Small** | Ideal: 50-100 lines, max: 300 |
| **Single Responsibility** | One reason to change |
| **High Cohesion** | Methods use all instance variables |
| **Low Coupling** | Depends on few other classes |
| **Organized for Change** | Changes in one area don't ripple |

### Cohesion Test

If a class has methods that use some instance variables but not others, it probably needs to be split.

```python
# BAD: Low cohesion — some methods don't use all fields
class User:
    def __init__(self, name, email, password_hash):
        self.name = name
        self.email = email
        self.password_hash = password_hash
    
    def validate_password(self, password):  # uses password_hash only
        ...
    def send_welcome_email(self):  # uses email only
        ...

# GOOD: High cohesion — each class uses all its fields
class PasswordAuthenticator:
    def __init__(self, password_hash):
        self.password_hash = password_hash
    
    def validate(self, password):
        ...

class UserNotifier:
    def send_welcome(self, email):
        ...
```

---

## VII. Code Smells & Heuristics (Top 20)

### Naming

| Smell | Description | Fix |
|-------|-------------|-----|
| **N1: Choose descriptive names** | Name reveals intent | Refactor until name is obvious |
| **N2: Appropriate abstraction level** | Name should match abstraction | Don't use implementation details in names |
| **N3: Standard nomenclature** | Use known patterns | `Command`, `Observer`, `Adapter` |
| **N4: Unambiguous names** | No confusion possible | One concept = one name |
| **N5: Long names for long scopes** | Scope size ↔ name length | Short scope = `i`, long scope = `index` |
| **N6: Avoid encodings** | No Hungarian, no prefixes | `m_`, `I`, `C` prefixes are noise |

### Functions

| Smell | Description | Fix |
|-------|-------------|-----|
| **F1: Too Many Arguments** | > 2 positional args | Use argument object |
| **F2: Output Arguments** | Modifying passed objects | Return new objects |
| **F3: Flag Arguments** | Boolean parameters | Split into two functions |
| **F4: Dead Function** | Never called | Delete |

### General

| Smell | Description | Fix |
|-------|-------------|-----|
| **G5: Duplication** | Same code in multiple places | Extract to shared function/class |
| **G6: Wrong Abstraction Level** | Code at wrong level | Refactor to consistent abstraction |
| **G8: Too Much Information** | Class exposes too much | Encapsulate, hide implementation |
| **G9: Dead Code** | Unused variables, methods, imports | Delete |
| **G11: Inconsistency** | Different conventions in same codebase | Pick one, apply everywhere |
| **G14: Feature Envy** | Method uses other class's data more than its own | Move method to the class it envies |
| **G17: Misplaced Responsibility** | Code in wrong class | Move to where it belongs |
| **G19: Use Explanatory Variables** | Complex expressions | Extract to named variables |
| **G23: Prefer Polymorphism to If/Else** | Type-switching logic | Use polymorphic dispatch |
| **G25: Replace Magic Numbers** | `if status == 3` | `if status == OrderStatus.CONFIRMED` |
| **G28: Encapsulate Conditionals** | Complex if conditions | Extract to `isReady()`, `isValid()` |
| **G29: Avoid Negative Conditionals** | `if not is_invalid` | `if is_valid` |
| **G30: Functions Do One Thing** | Multiple responsibilities | Extract sub-functions |
| **G34: One Level of Abstraction** | Mixed abstraction levels | Step-down rule |

---

## VIII. Implementation Checklist

When writing or reviewing code:

- [ ] **Names** — Would a stranger understand what this variable/function/class does?
- [ ] **Function size** — Is each function doing ONE thing? Is it small?
- [ ] **Arguments** — Can I reduce the number of arguments?
- [ ] **Comments** — Am I explaining WHAT instead of WHY?
- [ ] **Error handling** — Are error paths clean and separated from logic?
- [ ] **Tests** — Can I write a failing test before production code?
- [ ] **Class cohesion** — Do all methods in this class use all its fields?
- [ ] **Duplication** — Is the same logic repeated anywhere?
- [ ] **Magic numbers** — Are all literals named constants?
- [ ] **Negatives** — Am I using `if not` when `if` would be clearer?

---

## Common Pitfalls

1. **Commenting bad code instead of fixing it.** Comments are a last resort, not a crutch. If you need to explain what code does, rewrite it to be self-explanatory.

2. **Premature abstraction.** Don't abstract until you see the pattern at least 3 times. Premature abstraction is worse than duplication.

3. **"Clean enough" mentality.** Clean code is not about perfection — it's about caring. A function that's 25 lines when it could be 10 is "clean enough" — but don't let that slide into 100 lines.

4. **Over-engineering.** Simple code that works is better than clever code that's "correct." Follow the YAGNI principle (You Aren't Gonna Need It).

5. **Ignoring the Boy Scout Rule.** "Leave the code better than you found it." Every time you touch code, make it slightly cleaner.

## Verification Checklist

- [ ] Every function does ONE thing
- [ ] Every function is small (3-20 lines)
- [ ] Every name reveals intent
- [ ] No magic numbers — all named constants
- [ ] No commented-out code
- [ ] No null returns — use exceptions or Null Object
- [ ] Tests follow F.I.R.S.T. principles
- [ ] Classes follow SRP (one reason to change)
- [ ] No duplication
- [ ] Abstraction level is consistent within functions

## References

- Martin, R.C. (2008). *Clean Code: A Handbook of Agile Software Craftsmanship* — Prentice Hall
- Beck, K. (2008). *Implementation Patterns* — Addison-Wesley
- Fowler, M. (1999). *Refactoring: Improving the Design of Existing Code* — Addison-Wesley
- Martin, R.C. (2017). *Clean Architecture* — Prentice Hall
