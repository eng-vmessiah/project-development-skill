---
name: ddd-development
description: "Use when designing or refactoring code with Domain-Driven Design patterns. Covers strategic (Bounded Contexts, Context Maps) and tactical (Entities, Value Objects, Aggregates, Repositories, Services, Events, Modules, Factories) design with decision trees and code examples."
version: 1.0.0
license: MIT
metadata:
  hermes:
    tags: [ddd, domain-driven-design, modeling, architecture, patterns]
    related_skills: [clean-code, pd, design-patterns, database-patterns, auth-patterns]
---

# Domain-Driven Development (DDD)

## Overview

DDD is a software design approach that places the **business domain** at the center of all design decisions. The core idea: your code should be a direct reflection of the business domain, using a **Ubiquitous Language** shared between developers and domain experts.

This skill covers both **Strategic Design** (system boundaries, team relationships) and **Tactical Design** (building blocks of the domain model).

**Sources:** Eric Evans (DDD Reference), Vaughn Vernon (Implementing DDD), DDD Quickly.

## When to Use

- Starting a new feature that involves complex business logic
- Refactoring code that has become a "Big Ball of Mud"
- Designing microservices or modular monoliths
- Integrating with external systems (legacy, third-party)
- Team needs a shared vocabulary for a domain

**Don't use for:**
- Simple CRUD with no business rules
- Pure infrastructure/data pipeline code
- Prototypes where domain is not yet understood

---

## I. Strategic Design (The Big Picture)

### Domain, Subdomain, Bounded Context

| Concept | Definition | Question to Ask |
|---------|-----------|-----------------|
| **Domain** | The business sphere (e.g., banking, e-commerce) | "What problem are we solving?" |
| **Subdomain** | A distinct area within the domain | "Which specific business capability?" |
| **Core Domain** | The primary differentiator — where value is created | "What makes us unique?" |
| **Generic Subdomain** | Support function (auth, logging, email) | "Can we buy/build this generically?" |
| **Bounded Context** | Boundary where a specific model applies | "Who speaks this language?" |

### Bounded Context Rules

1. **One model per context** — don't share models across boundaries
2. **One Ubiquitous Language per context** — terms mean one thing only
3. **Integrate via APIs/events** — never share databases directly
4. **Size by team** — a context should be maintainable by 1-2 teams

### Context Map Patterns

| Pattern | When to Use | Relationship |
|---------|------------|--------------|
| **Partnership** | Both teams must succeed together | Mutual dependency |
| **Shared Kernel** | Common model subset between contexts | Tight coupling, small area |
| **Customer/Supplier** | Upstream provides, downstream consumes | Upstream > downstream |
| **Conformist** | Downstream must adapt to upstream model | No negotiation |
| **Anticorruption Layer** | Translate external model to your own | Defensive translation |
| **Open Host Service** | Upstream offers a public API/protocol | One-to-many |
| **Published Language** | Shared language for integration (JSON, XML) | Standardized |
| **Separate Ways** | No integration needed | Independent |

### Anticorruption Layer (ACL) — When Integrating Legacy/External

```
[Your Model] → [ACL Translation] → [External/Legacy Model]
```

The ACL translates between your Ubiquitous Language and the foreign model. **Never let external models pollute your domain.**

---

## II. Tactical Design (Building Blocks)

### Decision Tree: What Is This Concept?

```
Is it a thing with identity that changes over time?
  → YES → Entity
  → NO ↓

Is it a descriptor/measurement/composition of attributes?
  → YES → Value Object
  → NO ↓

Is it a process/transformation that doesn't fit on an Entity or VO?
  → YES → Domain Service
  → NO ↓

Is it something that happened (past tense)?
  → YES → Domain Event
  → NO ↓

Is it a container for related Entities/VOs with a consistency boundary?
  → YES → Aggregate
  → NO ↓

Is it a collection of cohesive domain objects?
  → YES → Module
```

### Entities

**Definition:** Objects distinguished by their **identity**, not attributes.

```python
class Order:
    def __init__(self, order_id: OrderId):
        self._id = order_id  # Identity is primary
        self._items: list[OrderItem] = []
        self._status = OrderStatus.PENDING
    
    def add_item(self, product_id: ProductId, quantity: int) -> None:
        # Business behavior, not just setters
        if self._status != OrderStatus.PENDING:
            raise CannotModifyConfirmedOrder()
        self._items.append(OrderItem(product_id, quantity))
```

**Rules:**
- Identity is immutable after creation
- Equality based on identity, not attributes
- Keep the class focused on lifecycle continuity
- Don't overuse — prefer Value Objects when identity doesn't matter

### Value Objects

**Definition:** Objects described by their **attributes**, with no conceptual identity.

```python
class Money:
    def __init__(self, amount: Decimal, currency: str):
        self.amount = amount
        self.currency = currency
    
    def add(self, other: Money) -> Money:
        if self.currency != other.currency:
            raise CurrencyMismatch()
        return Money(self.amount + other.amount, self.currency)
    
    def __eq__(self, other) -> bool:
        return self.amount == other.amount and self.currency == other.currency
```

**Rules:**
- **Immutable** — operations return new instances
- **Side-effect-free** — no observable state changes
- **Equality by value** — `a == b` if attributes match
- **Replaceable** — can swap one for another with same value
- Favor VOs over Entities — they're simpler and more testable

### Aggregates

**Definition:** A cluster of Entities and Value Objects treated as a **single unit** for data changes, with one **Aggregate Root**.

```python
class Order:  # Aggregate Root
    def __init__(self, order_id: OrderId):
        self._id = order_id
        self._items: list[OrderItem] = []
        self._shipping_address: Address = None
    
    def add_item(self, product_id: ProductId, qty: int) -> None:
        """Enforces invariant: max 10 items per order"""
        if len(self._items) >= 10:
            raise OrderItemLimitExceeded()
        self._items.append(OrderItem(product_id, qty))
```

**Aggregate Rules of Thumb (Vernon):**

1. **Model true invariants** — if two fields must be consistent, put them in the same Aggregate
2. **Design small Aggregates** — one root, minimal children (0-3)
3. **Reference other Aggregates by Identity** — `order.customer_id` not `order.customer`
4. **Use eventual consistency outside the boundary** — don't lock across Aggregates
5. **One Aggregate per transaction** — don't modify multiple Aggregates in one transaction

### Repositories

**Definition:** Provides the illusion of an in-memory collection of Aggregates.

```python
class OrderRepository(ABC):
    @abstractmethod
    def find_by_id(self, order_id: OrderId) -> Optional[Order]:
        """Retrieve a fully-instantiated Order Aggregate"""
        pass
    
    @abstractmethod
    def save(self, order: Order) -> None:
        """Persist the entire Aggregate"""
        pass
```

**Rules:**
- One Repository per Aggregate Root
- Return fully instantiated Aggregates (not partial)
- Encapsulate persistence technology (SQL, NoSQL, etc.)
- Interface uses Ubiquitous Language: `find_by_id`, `find_pending_orders`

### Domain Services

**Definition:** Operations that don't naturally belong to an Entity or Value Object.

```python
class PricingService:
    def calculate_discount(self, order: Order, customer: Customer) -> Money:
        """Cross-cutting logic involving multiple Aggregates"""
        base = order.total()
        if customer.is_vip():
            return base.multiply(0.9)
        return base
```

**When to use:**
- Operation involves multiple Aggregates
- Logic is a pure calculation/transformation
- Concept doesn't belong to any single Entity

**Don't use for:**
- Logic that belongs on an Entity (anemic domain model)
- Application-level concerns (use Application Services instead)

### Domain Events

**Definition:** Something that happened in the domain that experts care about.

```python
class OrderPlaced:
    def __init__(self, order_id: OrderId, customer_id: CustomerId, total: Money):
        self.order_id = order_id
        self.customer_id = customer_id
        self.total = total
        self.occurred_at = datetime.utcnow()

# In the Aggregate:
class Order:
    def confirm(self) -> OrderPlaced:
        self._status = OrderStatus.CONFIRMED
        return OrderPlaced(self._id, self._customer_id, self._total)
```

**Rules:**
- Events are **immutable** (past tense: `OrderPlaced`, not `PlaceOrder`)
- Published by Aggregates, subscribed by other parts of the system
- Used for integration between Bounded Contexts
- Carry identity and relevant data, not the full Aggregate

### Modules

**Definition:** Packages/namespaces that tell the **story of the system**.

```python
# Good: reflects domain concepts
ordering/
    customer.py
    order.py
    pricing.py
payment/
    invoice.py
    payment_method.py

# Bad: reflects technical layers
models/
    customer_model.py
    order_model.py
controllers/
    customer_controller.py
```

**Rules:**
- Names come from Ubiquitous Language
- High cohesion within, low coupling between
- Modules are part of the model, not just code organization

### Factories

**Definition:** Encapsulate complex object creation.

```python
class OrderFactory:
    @staticmethod
    def create_order(customer_id: CustomerId, items: list[dict]) -> Order:
        """Ensures Aggregate invariants are met on creation"""
        order = Order.generate_id()
        for item in items:
            order.add_item(ProductId(item['product']), item['qty'])
        return order
```

---

## III. Architecture Alignment

### Layered → Hexagonal → Clean

| Layer | Responsibility |
|-------|---------------|
| **Presentation** | UI, API controllers |
| **Application** | Use cases, orchestration |
| **Domain** | Business logic, models |
| **Infrastructure** | DB, messaging, external APIs |

**Key rule:** Domain layer has **zero dependencies** on other layers.

### CQRS (Command-Query Responsibility Segregation)

Separate read and write models when:
- Read and write patterns are very different
- You need optimized read queries (projections)
- Scaling reads independently from writes

```
Command → Domain Model → Write DB
                                    → Event → Read Projection → Read DB
Query → Read Model → Read DB
```

### Event Sourcing

Store state as a sequence of events, not current state:
- Full audit trail
- Temporal queries ("what was the state at time T?")
- Replay to rebuild state
- Natural fit with DDD Aggregates

---

## IV. Supple Design Principles

| Principle | What It Means |
|-----------|--------------|
| **Intention-Revealing Interfaces** | Names describe what, not how |
| **Side-Effect-Free Functions** | Operations return results without mutation |
| **Assertions** | Preconditions, postconditions, invariants |
| **Standalone Classes** | Minimal dependencies |
| **Closure of Operations** | `a.op(b)` returns same type as `a` |
| **Conceptual Contours** | Decompose along natural domain boundaries |

---

## V. Common Anti-Patterns & Fixes

| Anti-Pattern | Problem | Fix |
|-------------|---------|-----|
| **Anemic Domain Model** | Entities are just data, logic in services | Move behavior back into Entities |
| **Big Ball of Mud** | No clear boundaries or model | Introduce Bounded Contexts |
| **God Aggregate** | Huge Aggregate with 20+ objects | Split into smaller, identity-referenced Aggregates |
| **ORM Leak** | Database structure drives model | Design model first, persist separately |
| **Translation Layers Everywhere** | Every boundary has ACL | Use Shared Kernel or Published Language where possible |
| **Generic Everywhere** | Everything is "generic" | Identify Core Domain and invest there |

---

## VI. Implementation Checklist

When implementing a new domain feature:

- [ ] **Identify the Bounded Context** — which part of the domain?
- [ ] **Define the Ubiquitous Language** — what terms do domain experts use?
- [ ] **Choose your building blocks** — Entity? VO? Service? Event?
- [ ] **Design the Aggregate** — what's the consistency boundary?
- [ ] **Define the Repository interface** — what queries do you need?
- [ ] **Identify invariants** — what must always be true?
- [ ] **Write tests** — test the model, not the infrastructure
- [ ] **Consider integration** — events? ACL? Published Language?

---

## VII. Quick Reference: Naming

| Building Block | Naming Pattern | Examples |
|---------------|----------------|----------|
| Entity | Domain noun | `Order`, `Customer`, `Product` |
| Value Object | Domain concept/adjective | `Money`, `Address`, `EmailAddress` |
| Aggregate Root | Parent entity | `Order` (root of Order + OrderItems) |
| Repository | `I{Root}Repository` or `{Root}Repository` | `OrderRepository` |
| Domain Service | `{Verb}{Noun}` or `{Concept}Service` | `PricingService`, `TransferMoney` |
| Domain Event | `{Noun}{PastTenseVerb}` | `OrderPlaced`, `PaymentReceived` |
| Module | Domain subdomain | `ordering`, `payment`, `inventory` |
| Factory | `{Root}Factory` | `OrderFactory` |

---

## Common Pitfalls

1. **Starting with technology instead of domain.** Always begin with "What is the business trying to achieve?" — not "What framework should we use?"

2. **Overusing Entities.** Most concepts are better modeled as Value Objects. Use the decision tree: "Does this need identity?" If no, make it a VO.

3. **God Aggregates.** Vernon's rule: if your Aggregate has more than 3-5 objects, you probably have false invariants. Split it and reference by identity.

4. **Ignoring Bounded Contexts.** The #1 cause of "DDD doesn't work" is trying to use one model everywhere. Different contexts legitimately need different models.

5. **Leaking infrastructure into domain.** The domain layer should have ZERO imports from infrastructure (no database, no HTTP, no framework). Use dependency inversion.

6. **Skipping the Ubiquitous Language.** If your code uses different terms than your domain experts, you're building the wrong model. Refactor names ruthlessly.

## Verification Checklist

- [ ] Each Aggregate has exactly one Root entity
- [ ] Aggregates reference each other by Identity (not object reference)
- [ ] Repository interfaces use Ubiquitous Language
- [ ] Domain Events are immutable and named in past tense
- [ ] Value Objects are immutable and have side-effect-free operations
- [ ] Domain layer has no infrastructure imports
- [ ] Tests verify business rules, not persistence
- [ ] Bounded Context boundaries are clearly defined

## References
- Evans, E. (2015). *DDD Reference* — Definitions and Pattern Summaries
- Vernon, V. (2013). *Implementing Domain-Driven Design* — Addison-Wesley
- Avram, F. (2006). *Domain-Driven Design Quickly* — InfoQ

**Support files:**
- `references/patterns-summary.md` — Full pattern catalog extracted from all 3 books, decision trees, Vernon's Aggregate rules, anti-patterns table

## Related Skills

- **clean-code** — Naming, functions, and error handling apply directly to DDD building blocks.
- **pd** — Master orchestrator. DDD design happens during Phase 1 (Brainstorming) and Phase 2 (Planning).
- **design-patterns** — GoF patterns like Repository (Factory + Strategy), Factory for Aggregate Roots, Observer for Domain Events.
- **database-patterns** — Schema design, indexing, and migration patterns for persisting Aggregates.
- **auth-patterns** — Authentication and authorization. Model permissions within Bounded Contexts.
