# Philosophy

The principles and values behind Project Development Skills.

## Core Principles

### 1. Evidence Over Claims

> "No completion claims without fresh verification evidence."

- Don't say "it works" — show proof
- Run tests, show output
- Verify in this context, not previous

### 2. Process Over Speed

> "No code without specification + plan first."

- Even "simple" tasks need design
- The spec can be short, but it MUST exist
- Planning saves time in the long run

### 3. Quality Over Quantity

> "Bug-driven coverage over 100% coverage."

- Test where bugs were found
- Focus on critical paths
- Don't chase metrics

### 4. Clarity Over Cleverness

> "Write code for humans, not compilers."

- Clear names > clever abstractions
- Simple solutions > complex patterns
- Self-documenting code > comments

### 5. Independence Over Coupling

> "Each skill should stand alone."

- Skills work independently
- Cross-references are optional
- No hard dependencies

## Design Values

### Modularity

Each skill is a self-contained knowledge module:
- Single responsibility
- Clear boundaries
- Optional integration

### Composability

Skills combine to form workflows:
- pd orchestrates other skills
- Skills reference each other
- Users choose which skills to load

### Accessibility

Skills work across platforms:
- Hermes Agent
- OpenCode
- Claude Code

One format, three platforms.

### Evolvability

Skills can be improved over time:
- Version numbers track changes
- Cross-references enable discovery
- Community contributions welcome

## The PD Pipeline Philosophy

The PD pipeline embodies these principles:

```
Brainstorming → Understanding the problem
     ↓
Planning → Deciding the approach
     ↓
Structure → Organizing the work
     ↓
Coding → Implementing the solution
     ↓
Testing → Verifying correctness
     ↓
Validation → Confirming value
     ↓
Merge → Delivering results
```

Each phase:
1. Has clear inputs and outputs
2. Can be skipped for simple tasks
3. Builds on previous phases
4. Produces documentation

## Anti-Philosophy

What we DON'T believe:

### ❌ "Move Fast and Break Things"

We believe in moving deliberately and maintaining quality.

### ❌ "100% Test Coverage"

We believe in testing where it matters.

### ❌ "Premature Optimization"

We believe in measuring first, optimizing second.

### ❌ "Clever Code"

We believe in clear, maintainable code.

### ❌ "Copy-Paste Programming"

We believe in reusable patterns and skills.

## Community Values

### Respect

- Constructive feedback
- No personal attacks
- Assume good intent

### Quality

- High standards
- Thorough review
- Continuous improvement

### Inclusivity

- Welcome all skill levels
- Clear documentation
- Patient explanation

## References

These principles are inspired by:

- **Clean Code** — Robert C. Martin
- **Domain-Driven Design** — Eric Evans
- **The Pragmatic Programmer** — Hunt & Thomas
- **Refactoring** — Martin Fowler
- **Test Driven Development** — Kent Beck
