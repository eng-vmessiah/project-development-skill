---
name: codebase-design
description: Shared vocabulary for designing deep modules — depth, seams, adapters, testability. Inspirado por mattpocock/skills.
version: 1.0.0
metadata:
  source: github.com/mattpocock/skills
---

# Codebase Design

Design **deep modules**: a lot of behaviour behind a small interface, placed at a clean seam, testable through that interface.

## Glossary

Use these terms exactly:

**Module** — anything with an interface and an implementation. Scale-agnostic: function, class, package, or tier-spanning slice.

**Interface** — everything a caller must know to use the module correctly: type signature, invariants, ordering constraints, error modes, config, performance characteristics.

**Implementation** — what's inside a module, its body of code.

**Depth** — leverage at the interface: amount of behaviour per unit of interface the caller must learn. A module is **deep** when lots of behaviour sits behind a small interface, **shallow** when the interface is nearly as complex as the implementation.

**Seam** _(Michael Feathers)_ — a place where you can alter behaviour without editing in that place.

**Adapter** — a concrete thing that satisfies an interface at a seam.

**Leverage** — what callers get from depth: more capability per unit of interface learned.

**Locality** — what maintainers get from depth: change concentrates in one place.

## Deep vs shallow

```
Deep module:    Small Interface + Lots of Implementation  ✅
Shallow module: Large Interface + Thin Implementation     ❌
```

## Principles

- **Depth is a property of the interface, not the implementation.** A module can have internal seams (private, used by tests) + external seam (the public interface).
- **The deletion test.** Delete the module. If complexity reappears across N callers, it was earning its keep.
- **The interface is the test surface.** Callers and tests cross the same seam.
- **One adapter = hypothetical seam. Two adapters = real one.** Don't introduce a seam unless something actually varies across it.

## Designing for testability

1. **Accept dependencies, don't create them.** Pass in what you need.
2. **Return results, don't produce side effects.**
3. **Small surface area.** Fewer methods = fewer tests.

## Completion criterion

O módulo está desenhado com vocabulário consistente (module, interface, depth, seam), e a interface é menor que a implementação.
