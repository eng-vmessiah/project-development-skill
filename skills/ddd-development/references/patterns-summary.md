# DDD Patterns — Extracted Reference

## Strategic Patterns (Eric Evans Reference)

### Putting the Model to Work
- **Bounded Context**: Explicit boundary where a model applies. One model per context.
- **Ubiquitous Language**: Language structured around the domain model, used by all team members.
- **Continuous Integration**: Merge all code frequently with automated tests to flag fragmentation.
- **Model-Driven Design**: Code reflects domain model literally. Single model serves both purposes.
- **Hands-on Modelers**: Anyone contributing to model must touch code. Anyone changing code must learn the model.
- **Refactoring Toward Deeper Insight**: Iterative refactoring with domain experts to find incisive models.

### Building Blocks
- **Layered Architecture**: Isolate domain model from UI, database, infrastructure. Domain has zero dependencies upward.
- **Entities**: Distinguished by identity, not attributes. Thread of continuity through lifecycle.
- **Value Objects**: No conceptual identity. Immutable. Side-effect-free. Equality by value.
- **Domain Events**: Something happened that domain experts care about. Immutable record of past occurrence.
- **Services**: When operation doesn't fit naturally on Entity or VO. Stateless, defined by contract.
- **Modules**: Cohesive set of concepts. Names from Ubiquitous Language. Part of the model.
- **Aggregates**: Cluster with consistency boundary. One root entity. External references only to root.
- **Repositories**: Illusion of in-memory collection. One per Aggregate Root. Query access in Ubiquitous Language.
- **Factories**: Encapsulate complex assembly. Create entire Aggregate as piece, enforcing invariants.

### Supple Design
- **Intention-Revealing Interfaces**: Names describe effect/purpose, not means.
- **Side-Effect-Free Functions**: Operations return results with no observable state changes.
- **Assertions**: Post-conditions of operations, invariants of classes/aggregates.
- **Standalone Classes**: Eliminate all unnecessary dependencies.
- **Closure of Operations**: `a.op(b)` returns same type as `a`.
- **Declarative Design**: Executable specification style.

### Context Mapping
- **Partnership**: Mutual dependency, coordinated planning.
- **Shared Kernel**: Explicit shared subset of model/code. Small, tight.
- **Customer/Supplier**: Upstream provides, downstream consumes. Negotiated priorities.
- **Conformist**: Downstream adapts to upstream model slavishly.
- **Anticorruption Layer**: Defensive translation from foreign model.
- **Open Host Service**: Public API/protocol, one-to-many.
- **Published Language**: Standardized integration language (JSON, XML).
- **Separate Ways**: No integration needed.

### Distillation
- **Core Domain**: Primary differentiator, where value is created.
- **Generic Subdomains**: Support functions, buy/build generically.
- **Domain Vision Statement**: High-level summary of model's value.
- **Highlighted Core**: Visual emphasis on core in diagrams.
- **Cohesive Mechanisms**: Encapsulate domain mechanics.
- **Segregated Core**: Split core from generic into separate modules.
- **Abstract Core**: Abstract relationships in core domain.

## Vernon's Aggregate Rules (Implementing DDD)

1. **Model true invariants** in consistency boundaries
2. **Design small Aggregates** (one root, minimal children)
3. **Reference other Aggregates by Identity** (not object reference)
4. **Use eventual consistency outside** the Aggregate boundary
5. **One Aggregate per transaction** (don't modify multiple in one tx)

### Reasons to Break Rules (and when it's OK)
1. UI convenience — display optimization
2. Lack of technical mechanisms — framework limitations
3. Global transactions — unavoidable legacy integration
4. Query performance — read optimization

## Anti-Patterns to Watch

| Anti-Pattern | Signal | Fix |
|-------------|--------|-----|
| Anemic Domain Model | Entities are data containers, logic in services | Move behavior into entities |
| Big Ball of Mud | No clear boundaries | Introduce Bounded Contexts |
| God Aggregate | 20+ objects in one Aggregate | Split, reference by identity |
| DDD-Lite | Skipping strategic patterns (Bounded Context, Context Map) | Embrace full DDD |
| ORM Leak | Database structure drives model | Model first, persist separately |
| Translation Everywhere | ACL at every boundary | Use Shared Kernel/Published Language |

## Decision Tree: What Building Block?

```
Thing with identity changing over time?
  → Entity

Descriptor/measurement/attributes only?
  → Value Object

Process/transformation not on Entity/VO?
  → Domain Service

Something that happened (past tense)?
  → Domain Event

Container for related objects with consistency boundary?
  → Aggregate

Collection of cohesive domain objects?
  → Module
```
