---
name: documentation-patterns
description: "Documentation patterns — README structure, API docs, ADRs, code comments, changelogs, contributing guidelines. Use when writing, organizing, or improving project documentation."
version: 1.0.0
author: ISIS
license: MIT
metadata:
  hermes:
    tags: [documentation, readme, api-docs, adr, changelog, writing]
    related_skills: [clean-code, writing-clearly-and-concisely, pd]
---

# Documentation Patterns

## Overview

Documentation is a gift to your future self and your team. Write it like the reader has zero context and limited time. Good documentation answers "what is this?" and "how do I use it?" without requiring the reader to understand the codebase.

**Core principle:** If a reader has to read source code to understand your documentation, the documentation has failed.

## When to Use

- Creating or updating a README
- Writing API documentation
- Documenting architecture decisions
- Creating changelogs
- Writing contributing guidelines
- Adding code comments

**Don't over-document:**
- Obvious code (let the code speak)
- Implementation details that change frequently
- Things covered by automated tests

---

## I. README Structure

### Essential Sections

```markdown
# Project Name

One-line description of what this project does.

## Quick Start

<!-- 3-5 commands to get running -->

## Installation

<!-- Step-by-step setup -->

## Usage

<!-- How to use the project, with examples -->

## API Reference

<!-- If applicable, link to detailed docs -->

## Configuration

<!-- Environment variables, config files -->

## Contributing

<!-- How to contribute, link to CONTRIBUTING.md -->

## License

<!-- License type -->
```

### README Anti-Patterns

| Pattern | Problem | Fix |
|---------|---------|-----|
| Wall of text | Reader gives up | Use headers, bullets, code blocks |
| No quick start | 30-minute setup for simple project | Add 3-command quick start |
| Outdated screenshots | Confusing, wrong expectations | Use text-based examples |
| Missing examples | Reader can't try it | Add copy-pasteable examples |
| Jargon without context | Assumes knowledge | Define terms, link to resources |

### Good README Example

```markdown
# OrderFlow

Order processing API for e-commerce platforms.

## Quick Start

```bash
pip install orderflow
orderflow init --db postgresql://localhost/orders
orderflow serve
# API running at http://localhost:8000
```

## Usage

```python
from orderflow import OrderFlow

app = OrderFlow()

@app.post("/orders")
async def create_order(items: list[Item]):
    order = Order(items=items)
    await app.process(order)
    return {"order_id": order.id, "total": order.total}
```

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `sqlite:///orders.db` | Database connection string |
| `PORT` | `8000` | Server port |
| `LOG_LEVEL` | `info` | Logging level (debug/info/warning/error) |
```

---

## II. API Documentation

### OpenAPI/Swagger Structure

```yaml
openapi: 3.0.0
info:
  title: OrderFlow API
  version: 1.0.0
  description: Order processing API for e-commerce platforms.

paths:
  /orders:
    post:
      summary: Create a new order
      tags: [Orders]
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/CreateOrder'
            example:
              items:
                - product_id: "prod_123"
                  quantity: 2
      responses:
        '201':
          description: Order created successfully
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Order'
        '400':
          description: Invalid request
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Error'
```

### API Documentation Best Practices

```markdown
## POST /orders

Create a new order.

### Request

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| items | Item[] | Yes | List of items to order |
| items[].product_id | string | Yes | Product identifier |
| items[].quantity | integer | Yes | Quantity (min: 1) |
| notes | string | No | Order notes |

### Response (201)

| Field | Type | Description |
|-------|------|-------------|
| order_id | string | Unique order identifier |
| total | number | Order total in cents |
| status | string | Order status (pending/confirmed) |

### Errors

| Status | Code | Description |
|--------|------|-------------|
| 400 | invalid_items | One or more items are invalid |
| 400 | empty_order | Order must have at least one item |
| 429 | rate_limit | Too many requests |

### Example

```bash
curl -X POST https://api.example.com/orders \
  -H "Content-Type: application/json" \
  -d '{"items": [{"product_id": "prod_123", "quantity": 2}]}'
```
```

---

## III. Architecture Decision Records (ADRs)

### ADR Template

```markdown
# ADR-{number}: {title}

**Date:** YYYY-MM-DD
**Status:** Proposed | Accepted | Deprecated | Superseded by [ADR-{number}]

## Context

What is the issue that motivates this decision? What forces are at play?

## Decision

What is the change being proposed or decided?

## Consequences

### Positive
- {benefit 1}
- {benefit 2}

### Negative
- {tradeoff 1}
- {tradeoff 2}

### Risks
- {risk 1}

## Alternatives Considered

### {Alternative 1}
- Pros: ...
- Cons: ...

### {Alternative 2}
- Pros: ...
- Cons: ...
```

### ADR Examples

```markdown
# ADR-001: Use PostgreSQL as primary database

**Date:** 2024-01-15
**Status:** Accepted

## Context

We need a reliable, ACID-compliant database for the order processing system.
Data includes orders, products, users, and inventory with complex relationships.
We expect 10K orders/day at peak.

## Decision

Use PostgreSQL 16 as the primary database.

## Consequences

### Positive
- ACID compliance for financial transactions
- Rich query support (JSON, CTEs, window functions)
- Strong ecosystem and tooling
- Proven at scale

### Negative
- More operational complexity than SQLite
- Requires running a separate service

### Risks
- Schema migrations need careful testing

## Alternatives Considered

### SQLite
- Pros: Zero-config, embedded
- Concurrency limitations, no network access

### MongoDB
- Pros: Flexible schema
- No ACID transactions, weaker consistency guarantees
```

---

## IV. Code Comments

### The Golden Rule

> Explain WHY, not WHAT.

### Good Comments

```python
# WHY: Sort by timestamp to optimize subsequent binary search
results.sort(key=lambda x: x.timestamp)

# HACK: API returns 500 for valid empty responses (upstream bug, tracked in #1234)
if response.status_code == 500 and "no data" in response.text:
    return []

# TODO(Vitor): Migrate to new auth API when v2 is stable (2024-Q2)
token = old_auth_api.get_token(user_id)

# SECURITY: Never log full credit card numbers
logger.info(f"Payment processed for card ending in {card_number[-4:]}")
```

### Bad Comments

```python
# BAD: What the code does (redundant)
x = x + 1  # increment x

# BAD: Outdated/wrong information  
# Returns list of users
def get_active_users():  # Actually returns filtered list

# BAD: TODO without owner or timeline
# TODO: fix this later

# BAD: Commented-out code
# def old_function():
#     pass
```

### Comment Decision Tree

```
Does the code need explaining?
  → YES → Can you rename it to be self-explanatory?
    → YES → Rename, don't comment
    → NO → Add a comment explaining WHY
  → NO → Don't comment
```

---

## V. Changelog Format

### Keep a Changelog

```markdown
# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- New feature X that does Y

### Changed
- Improved performance of Z by 50%

### Deprecated
- Feature A will be removed in v2.0

### Removed
- Legacy endpoint /api/v1/old

### Fixed
- Bug where login fails with special characters in password

### Security
- Updated dependency to fix CVE-2024-1234

## [1.2.0] - 2024-01-15

### Added
- User registration endpoint
- Password reset flow

### Fixed
- Race condition in order processing
```

### Changelog Rules

- Group by type (Added, Changed, Deprecated, Removed, Fixed, Security)
- Use imperative mood ("Add feature" not "Added feature")
- Include issue/PR numbers for traceability
- Don't include internal implementation details
- Keep it human-readable

---

## VI. Contributing Guidelines

### CONTRIBUTING.md Template

```markdown
# Contributing to ProjectName

Thank you for your interest in contributing!

## Development Setup

1. Clone the repo
2. Install dependencies: `make install`
3. Run tests: `make test`
4. Start dev server: `make dev`

## Code Style

- Follow the existing code style
- Run `make lint` before committing
- All functions must have docstrings
- Tests required for new features

## Pull Request Process

1. Create a feature branch from `main`
2. Make your changes with tests
3. Run the full test suite
4. Submit PR with clear description
5. Wait for review (usually < 24h)

## Reporting Bugs

Use the issue template. Include:
- Steps to reproduce
- Expected behavior
- Actual behavior
- Environment details

## Code of Conduct

Be respectful. We're here to build great software together.
```

---

## VII. Documentation as Code

### Structure

```
docs/
├── README.md              # Quick start
├── getting-started/
│   ├── installation.md
│   └── first-project.md
├── guides/
│   ├── authentication.md
│   ├── deployment.md
│   └── troubleshooting.md
├── api/
│   ├── reference.md
│   └── examples.md
├── adr/
│   ├── 001-database-choice.md
│   └── 002-api-versioning.md
└── CONTRIBUTING.md
```

### Auto-Generated Docs

```python
# Sphinx auto-docstring
def calculate_discount(order: Order, customer: Customer) -> Money:
    """Calculate discount for an order based on customer tier.
    
    Args:
        order: The order to calculate discount for
        customer: The customer making the order
    
    Returns:
        The discount amount in the order's currency
    
    Raises:
        ValueError: If order total is negative
    
    Example:
        >>> order = Order(total=Money(100, "USD"))
        >>> customer = Customer(tier="gold")
        >>> calculate_discount(order, customer)
        Money(10, "USD")
    """
    if order.total.amount < 0:
        raise ValueError("Order total cannot be negative")
    
    discount_rate = TIER_DISCOUNTS.get(customer.tier, 0)
    return order.total.multiply(discount_rate)
```

### Link Checking

```bash
# Check for broken links
npx markdown-link-check docs/**/*.md

# Or with grep
grep -rn 'http[s]*://' docs/ | while read line; do
    url=$(echo "$line" | grep -oP 'https?://[^\s)]+')
    curl -sI "$url" | head -1
done
```

---

## Anti-Patterns

| Pattern | Problem | Fix |
|---------|---------|-----|
| Documentation debt | Docs fall behind code | Make docs part of PR review |
| Wall of text | Nobody reads it | Use headers, bullets, code blocks |
| Missing examples | Can't try without reading code | Add copy-pasteable examples |
| Outdated screenshots | Confusing, wrong expectations | Use text-based examples |
| No ADRs | Decisions lost to time | Write ADR for every significant choice |
| Jargon without context | Assumes knowledge | Define terms, link to resources |

## Verification Checklist

- [ ] README has Quick Start section (3-5 commands)
- [ ] API docs include request/response examples
- [ ] ADRs exist for significant architectural decisions
- [ ] Code comments explain WHY, not WHAT
- [ ] Changelog follows Keep a Changelog format
- [ ] CONTRIBUTING.md has clear setup and PR instructions
- [ ] Documentation is tested (link check, build)

## Related Skills

- **clean-code** — Self-documenting code reduces need for comments. Clear names and small functions speak for themselves.
- **writing-clearly-and-concisely** — Active voice, concrete language, omit needless words. Apply to all documentation.
- **pd** — Master orchestrator. Documentation is created during Phase 1 (Brainstorming) and maintained throughout.
