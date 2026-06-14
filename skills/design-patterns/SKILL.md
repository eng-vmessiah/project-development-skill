---
name: design-patterns
description: "Design patterns reference — GoF 23 patterns, decision trees, anti-patterns, and practical examples. Use when designing architecture, choosing abstractions, or refactoring code."
version: 1.0.0
author: ISIS
license: MIT
metadata:
  hermes:
    tags: [design-patterns, architecture, gof, oop, refactoring]
    related_skills: [clean-code, ddd-development, pd, systematic-debugging]
---

# Design Patterns — GoF Reference

## Overview

Design patterns are proven solutions to recurring software design problems. They provide a shared vocabulary and tested approaches for common challenges.

**Source:** Based on "Design Patterns: Elements of Reusable Object-Oriented Software" (Gamma, Helm, Johnson, Vlissides, 1994) — the Gang of Four (GoF).

## When to Use

- Designing new architecture
- Refactoring existing code
- Choosing abstractions
- Solving communication problems between components
- Making code more flexible and maintainable

## The 23 GoF Patterns

### Classification

| Category | Purpose | Patterns |
|----------|---------|----------|
| **Creational** | Object creation mechanisms | Singleton, Factory Method, Abstract Factory, Builder, Prototype |
| **Structural** | Object composition | Adapter, Bridge, Composite, Decorator, Façade, Flyweight, Proxy |
| **Behavioral** | Object communication | Chain of Responsibility, Command, Iterator, Mediator, Memento, Observer, State, Strategy, Template Method, Visitor, Interpreter |

### Quick Reference

| Pattern | Category | Problem It Solves | When to Use |
|---------|----------|-------------------|-------------|
| **Singleton** | Creational | Ensure single instance | Global state, resource management |
| **Factory Method** | Creational | Let subclasses decide instantiation | Framework extensibility |
| **Abstract Factory** | Creational | Create families of related objects | Platform independence |
| **Builder** | Creational | Construct complex objects step by step | Many optional parameters |
| **Prototype** | Creational | Clone existing objects | Expensive object creation |
| **Adapter** | Structural | Convert one interface to another | Integration, legacy code |
| **Bridge** | Structural | Decouple abstraction from implementation | Multiple dimensions of variation |
| **Composite** | Structural | Tree structures with uniform treatment | UI hierarchies, file systems |
| **Decorator** | Structural | Add behavior dynamically | Open/closed principle |
| **Façade** | Structural | Simplify complex subsystems | API design, complexity hiding |
| **Flyweight** | Structural | Share common state efficiently | Memory optimization |
| **Proxy** | Structural | Control access to another object | Lazy loading, access control |
| **Chain of Responsibility** | Behavioral | Pass requests along a chain | Logging, auth, middleware |
| **Command** | Behavioral | Encapsulate requests as objects | Undo/redo, queues |
| **Iterator** | Behavioral | Sequential access without exposing internals | Collections traversal |
| **Mediator** | Behavioral | Reduce direct dependencies between objects | Complex interactions |
| **Memento** | Behavioral | Capture and restore state | Undo systems |
| **Observer** | Behavioral | Notify dependents of state changes | Event systems, reactive |
| **State** | Behavioral | Alter behavior when state changes | Finite state machines |
| **Strategy** | Behavioral | Swap algorithms at runtime | Algorithm selection |
| **Template Method** | Behavioral | Define skeleton, let subclasses fill steps | Code reuse, hooks |
| **Visitor** | Behavioral | Add operations without modifying classes | Traversal with operations |
| **Interpreter** | Behavioral | Grammar interpretation | DSLs, parsers |

---

## Essential Patterns (Top 7)

These patterns appear most frequently in modern software development.

### 1. Strategy Pattern

**Problem:** Multiple algorithms for the same task, need to switch at runtime.

**Solution:** Define a family of algorithms, encapsulate each one, make them interchangeable.

```python
# Strategy interface
class SortStrategy:
    def sort(self, data: list) -> list:
        raise NotImplementedError

# Concrete strategies
class QuickSort(SortStrategy):
    def sort(self, data: list) -> list:
        # QuickSort implementation
        return sorted(data)

class MergeSort(SortStrategy):
    def sort(self, data: list) -> list:
        # MergeSort implementation
        return sorted(data)

# Context
class Sorter:
    def __init__(self, strategy: SortStrategy):
        self._strategy = strategy
    
    def set_strategy(self, strategy: SortStrategy):
        self._strategy = strategy
    
    def sort(self, data: list) -> list:
        return self._strategy.sort(data)

# Usage
sorter = Sorter(QuickSort())
result = sorter.sort([3, 1, 4, 1, 5, 9])

# Switch strategy at runtime
sorter.set_strategy(MergeSort())
result = sorter.sort([3, 1, 4, 1, 5, 9])
```

**Anti-patterns:**
- Don't use when there's only one algorithm
- Don't over-engineer simple conditionals

---

### 2. Observer Pattern

**Problem:** One object changes, many need to be notified.

**Solution:** Define a subscription mechanism to notify multiple objects.

```python
from typing import List, Callable

class EventEmitter:
    def __init__(self):
        self._listeners: dict[str, List[Callable]] = {}
    
    def on(self, event: str, callback: Callable):
        if event not in self._listeners:
            self._listeners[event] = []
        self._listeners[event].append(callback)
    
    def emit(self, event: str, *args, **kwargs):
        for callback in self._listeners.get(event, []):
            callback(*args, **kwargs)

# Usage
emitter = EventEmitter()

def on_user_created(user):
    print(f"Welcome, {user['name']}!")

def send_welcome_email(user):
    print(f"Sending email to {user['email']}")

emitter.on("user_created", on_user_created)
emitter.on("user_created", send_welcome_email)

emitter.emit("user_created", {"name": "Alice", "email": "alice@example.com"})
```

**Anti-patterns:**
- Don't use for simple 1:1 relationships
- Be careful with memory leaks (unsubscribing)

---

### 3. Factory Method Pattern

**Problem:** Object creation logic needs to be flexible.

**Solution:** Define an interface for creating objects, let subclasses decide which class to instantiate.

```python
from abc import ABC, abstractmethod

# Product interface
class Notification(ABC):
    @abstractmethod
    def send(self, message: str) -> bool:
        pass

# Concrete products
class EmailNotification(Notification):
    def send(self, message: str) -> bool:
        print(f"📧 Sending email: {message}")
        return True

class SlackNotification(Notification):
    def send(self, message: str) -> bool:
        print(f"💬 Sending Slack: {message}")
        return True

class SMSNotification(Notification):
    def send(self, message: str) -> bool:
        print(f"📱 Sending SMS: {message}")
        return True

# Creator
class NotificationFactory:
    @staticmethod
    def create(notification_type: str) -> Notification:
        factories = {
            "email": EmailNotification,
            "slack": SlackNotification,
            "sms": SMSNotification,
        }
        return factories[notification_type]()

# Usage
notification = NotificationFactory.create("email")
notification.send("Hello!")
```

**Anti-patterns:**
- Don't use when there's only one product
- Don't over-engineer with factory for simple classes

---

### 4. Decorator Pattern

**Problem:** Add responsibilities to objects dynamically.

**Solution:** Attach additional responsibilities to an object by wrapping it.

```python
from typing import Callable

# Component interface
def text_processor(text: str) -> str:
    return text

# Decorators
def uppercase(func: Callable) -> Callable:
    def wrapper(text: str) -> str:
        return func(text).upper()
    return wrapper

def exclaim(func: Callable) -> Callable:
    def wrapper(text: str) -> str:
        return func(text) + "!"
    return wrapper

def repeat(func: Callable) -> Callable:
    def wrapper(text: str) -> str:
        return func(text) + " " + func(text)
    return wrapper

# Usage
@uppercase
@exclaim
@repeat
def greet(name: str) -> str:
    return f"Hello {name}"

print(greet("World"))  # "HELLO WORLD! HELLO WORLD!"
```

**Pythonic version:** Use `functools.wraps` for better decorator behavior.

**Anti-patterns:**
- Don't use when inheritance is simpler
- Don't stack too many decorators (hard to debug)

---

### 5. Adapter Pattern

**Problem:** Incompatible interfaces need to work together.

**Solution:** Convert the interface of a class into another interface clients expect.

```python
# Old interface
class OldPaymentSystem:
    def make_payment(self, amount: float, currency: str) -> bool:
        print(f"Old system: {amount} {currency}")
        return True

# New interface
class NewPaymentSystem:
    def pay(self, amount: float, currency: str, method: str) -> dict:
        print(f"New system: {amount} {currency} via {method}")
        return {"status": "success"}

# Adapter
class PaymentAdapter:
    def __init__(self, old_system: OldPaymentSystem):
        self._old_system = old_system
    
    def pay(self, amount: float, currency: str, method: str = "card") -> dict:
        # Adapt new interface to old
        success = self._old_system.make_payment(amount, currency)
        return {"status": "success" if success else "failed"}

# Usage
old_system = OldPaymentSystem()
adapter = PaymentAdapter(old_system)

# Now works with new interface
result = adapter.pay(100.00, "USD", "card")
```

**Anti-patterns:**
- Don't use when you can modify the original class
- Don't over-adapter (sometimes direct integration is better)

---

### 6. Builder Pattern

**Problem:** Complex object with many optional parameters.

**Solution:** Separate construction from representation, allowing step-by-step construction.

```python
from dataclasses import dataclass
from typing import Optional

@dataclass
class HTTPRequest:
    method: str
    url: str
    headers: dict
    body: Optional[str] = None
    timeout: int = 30
    retries: int = 3

class HTTPRequestBuilder:
    def __init__(self, method: str, url: str):
        self._method = method
        self._url = url
        self._headers = {}
        self._body = None
        self._timeout = 30
        self._retries = 3
    
    def header(self, key: str, value: str) -> "HTTPRequestBuilder":
        self._headers[key] = value
        return self
    
    def body(self, body: str) -> "HTTPRequestBuilder":
        self._body = body
        return self
    
    def timeout(self, seconds: int) -> "HTTPRequestBuilder":
        self._timeout = seconds
        return self
    
    def retries(self, count: int) -> "HTTPRequestBuilder":
        self._retries = count
        return self
    
    def build(self) -> HTTPRequest:
        return HTTPRequest(
            method=self._method,
            url=self._url,
            headers=self._headers,
            body=self._body,
            timeout=self._timeout,
            retries=self._retries
        )

# Usage (fluent API)
request = (
    HTTPRequestBuilder("POST", "https://api.example.com/users")
    .header("Content-Type", "application/json")
    .header("Authorization", "Bearer token123")
    .body('{"name": "Alice"}')
    .timeout(60)
    .retries(5)
    .build()
)
```

**Anti-patterns:**
- Don't use for simple objects with few parameters
- Don't use when constructor parameters are required

---

### 7. Proxy Pattern

**Problem:** Need to control access to an object (lazy loading, access control, logging).

**Solution:** Provide a surrogate or placeholder for another object.

```python
from typing import Optional
from abc import ABC, abstractmethod

# Subject interface
class Database(ABC):
    @abstractmethod
    def query(self, sql: str) -> list:
        pass

# Real subject
class RealDatabase(Database):
    def __init__(self, connection_string: str):
        print("🔌 Connecting to database...")
        # Expensive connection
        self.connection = connection_string
    
    def query(self, sql: str) -> list:
        print(f"🔍 Executing: {sql}")
        return [{"id": 1, "name": "Alice"}]

# Proxy
class DatabaseProxy(Database):
    def __init__(self, connection_string: str):
        self._connection_string = connection_string
        self._real_db: Optional[RealDatabase] = None
    
    def query(self, sql: str) -> list:
        # Lazy initialization
        if self._real_db is None:
            self._real_db = RealDatabase(self._connection_string)
        return self._real_db.query(sql)

# Usage
db = DatabaseProxy("postgresql://localhost/mydb")
# Database not connected yet
result = db.query("SELECT * FROM users")  # Now it connects
```

**Proxy Types:**
- **Virtual:** Lazy loading (shown above)
- **Remote:** Local representative for remote object
- **Protection:** Access control
- **Smart reference:** Reference counting, locking

**Anti-patterns:**
- Don't use when direct access is fine
- Don't add unnecessary indirection

---

## Decision Tree: Which Pattern to Use?

```
START
  │
  ├─ Need to create objects?
  │   ├─ Single instance? → Singleton
  │   ├─ Multiple related objects? → Abstract Factory
  │   ├─ Complex construction? → Builder
  │   ├─ Subclasses decide? → Factory Method
  │   └─ Clone existing? → Prototype
  │
  ├─ Need to compose objects?
  │   ├─ Incompatible interfaces? → Adapter
  │   ├─ Multiple abstractions? → Bridge
  │   ├─ Tree structures? → Composite
  │   ├─ Add responsibilities? → Decorator
  │   ├─ Simplify complex API? → Façade
  │   ├─ Memory optimization? → Flyweight
  │   └─ Control access? → Proxy
  │
  └─ Need to communicate between objects?
      ├─ Chain of handlers? → Chain of Responsibility
      ├─ Encapsulate requests? → Command
      ├─ Sequential access? → Iterator
      ├─ Reduce dependencies? → Mediator
      ├─ Save/restore state? → Memento
      ├─ Notify changes? → Observer
      ├─ State-dependent behavior? → State
      ├─ Swap algorithms? → Strategy
      ├─ Template with hooks? → Template Method
      ├─ Add operations? → Visitor
      └─ Parse grammar? → Interpreter
```

---

## Anti-Patterns: When NOT to Use

| Pattern | Don't Use When |
|---------|----------------|
| **Singleton** | Testing is important (hard to mock), multiple instances needed, global state is bad |
| **Factory Method** | Only one product, simple instantiation |
| **Abstract Factory** | No variation in product families |
| **Builder** | Few parameters, required parameters only |
| **Prototype** | Object creation is cheap |
| **Adapter** | You can modify the original class |
| **Bridge** | Only one implementation |
| **Composite** | Flat structure, no tree needed |
| **Decorator** | Inheritance is simpler |
| **Façade** | Subsystem is already simple |
| **Flyweight** | Few objects, memory isn't a concern |
| **Proxy** | Direct access is fine |
| **Chain of Responsibility** | Fixed handling order |
| **Command** | No undo/redo needed |
| **Iterator** | Built-in iteration is sufficient |
| **Mediator** | Interactions are simple |
| **Memento** | State is simple or immutable |
| **Observer** | Simple 1:1 relationship |
| **State** | Few states, simple transitions |
| **Strategy** | Few algorithms, no runtime switching |
| **Template Method** | No variation in algorithm steps |
| **Visitor** | Operations rarely change |
| **Interpreter** | No grammar to interpret |

---

## Patterns in Modern Frameworks

### React/Frontend
- **Observer:** Event handlers, state management (Redux)
- **Decorator:** Higher-Order Components (HOC)
- **Composite:** Component tree
- **Proxy:** React.lazy, Suspense

### Backend/API
- **Factory:** Dependency injection containers
- **Strategy:** Authentication methods, payment processors
- **Proxy:** ORM lazy loading, API rate limiting
- **Chain:** Middleware pipelines (Express, FastAPI)

### Python
- **Decorator:** `@property`, `@staticmethod`, `@cache`
- **Iterator:** Generator functions, `__iter__`
- **Context Manager:** `with` statement (Template Method)
- **Singleton:** Module-level instances

---

## Quick Reference Card

```
┌─────────────────────────────────────────────────────────────┐
│                    CREATIONAL                                │
├─────────────────────────────────────────────────────────────┤
│ Singleton    → One instance, global access                  │
│ Factory      → Create objects without specifying class      │
│ Abstract Factory → Families of related objects              │
│ Builder      → Complex objects step by step                 │
│ Prototype    → Clone existing objects                       │
├─────────────────────────────────────────────────────────────┤
│                    STRUCTURAL                                │
├─────────────────────────────────────────────────────────────┤
│ Adapter      → Convert interface A to interface B           │
│ Bridge       → Decouple abstraction from implementation     │
│ Composite    → Tree of uniform components                   │
│ Decorator    → Add behavior dynamically                     │
│ Façade       → Simplify complex subsystem                   │
│ Flyweight    → Share common state                           │
│ Proxy        → Control access to object                     │
├─────────────────────────────────────────────────────────────┤
│                    BEHAVIORAL                                │
├─────────────────────────────────────────────────────────────┤
│ Chain        → Pass request along chain                     │
│ Command      → Encapsulate request as object                │
│ Iterator     → Traverse collection                          │
│ Mediator     → Centralize complex communication             │
│ Memento      → Save/restore state                           │
│ Observer     → Notify dependents                            │
│ State        → Behavior changes with state                  │
│ Strategy     → Swap algorithms                              │
│ Template     → Define skeleton, fill in steps               │
│ Visitor      → Add operations without modification          │
│ Interpreter  → Parse grammar                                │
└─────────────────────────────────────────────────────────────┘
```

---

## Integration with Skills

### clean-code
- Use **Strategy** instead of switch statements
- Use **Decorator** instead of inheritance hierarchies
- Use **Factory** for complex object creation

### ddd-development
- **Repository** pattern (Factory + Strategy)
- **Factory** for aggregate roots
- **Observer** for Domain Events
- **Strategy** for domain logic variation

### pd (Planning)
- Reference patterns in Phase 2 (Planning)
- Suggest patterns in Phase 4 (Coding)
- Review pattern usage in Phase 6 (Validation)

---

## References

- Gamma, E., Helm, R., Johnson, R., & Vlissides, J. (1994). *Design Patterns: Elements of Reusable Object-Oriented Software*. Addison-Wesley.
- Tushaar Gangarapu. *Design Patterns GoF*. (Source for this skill)
- Refactoring.Guru: https://refactoring.guru/design-patterns
- SourceMaking: https://sourcemaking.com/design_patterns
