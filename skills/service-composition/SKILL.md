---
name: service-composition
description: "Service composition patterns — Worker-Function-Trigger, live catalogs, event-driven architectures, agentic pipelines. Use when designing service integration, event flows, or distributed systems."
version: 1.0.0
author: ISIS
license: MIT
metadata:
  hermes:
    tags: [services, composition, event-driven, distributed, workers, triggers]
    related_skills: [design-patterns, monitoring-observability, deployment-patterns, pd]
---

# Service Composition Patterns

## Overview

Compose, extend, and observe services using three primitives: Worker, Function, Trigger.

**Based on:** iii framework patterns for zero-integration service composition.

## When to Use

- Designing service integration
- Building event-driven architectures
- Creating agentic pipelines
- Implementing distributed workflows
- Adding observability to services

---

## The Three Primitives

```
┌─────────────────────────────────────────────────────────────┐
│                    THREE PRIMITIVES                          │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│   WORKER ──► FUNCTION ──► TRIGGER                            │
│      │           │            │                              │
│   Process    Unit of Work   What causes                      │
│   that       with stable    function to                      │
│   registers  identifier     run                              │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### Worker

A process that registers with the system and exposes functions and triggers.

```python
# Python example
from service_composition import register_worker

worker = register_worker("order-service")

# Worker can register functions
@worker.function("orders::validate")
def validate_order(order):
    # Validation logic
    return {"valid": True}

# Worker can register triggers
@worker.trigger(type="http", path="/orders")
def handle_order_request(request):
    return worker.call("orders::validate", request.data)
```

```typescript
// TypeScript example
import { registerWorker } from "service-composition-sdk";

const worker = registerWorker("order-service");

worker.registerFunction("orders::validate", async (order) => {
  // Validation logic
  return { valid: true };
});
```

### Function

A unit of work with a stable identifier (e.g., `orders::validate`, `users::create`).

```python
# Function registration
@worker.function("orders::validate")
def validate_order(order: dict) -> dict:
    """Validate order data."""
    errors = []
    
    if not order.get("items"):
        errors.append("No items in order")
    
    if order.get("total", 0) <= 0:
        errors.append("Invalid total")
    
    return {
        "valid": len(errors) == 0,
        "errors": errors
    }

# Function with side effects
@worker.function("orders::charge")
def charge_order(order: dict) -> dict:
    """Charge payment for order."""
    # Process payment
    payment_result = process_payment(order["payment_method"], order["total"])
    
    return {
        "charged": payment_result["success"],
        "transaction_id": payment_result["id"]
    }
```

### Trigger

Anything that causes a function to run.

```python
# HTTP Trigger
@worker.trigger(type="http", path="/orders", method="POST")
def handle_create_order(request):
    return worker.call("orders::create", request.data)

# Cron Trigger
@worker.trigger(type="cron", schedule="0 9 * * *")
def daily_report():
    return worker.call("reports::daily")

# State Trigger (reactive)
@worker.trigger(type="state", scope="orders")
def on_order_change(event):
    """Triggered when order state changes."""
    if event["new_value"]["status"] == "paid":
        return worker.call("orders::ship", event["new_value"])

# Queue Trigger
@worker.trigger(type="queue", queue="order-processing")
def process_order(order):
    """Triggered when order added to queue."""
    return worker.call("orders::process", order)

# Stream Trigger
@worker.trigger(type="stream", stream="order-events")
def handle_stream_event(event):
    """Triggered on stream events."""
    return worker.call("events::process", event)
```

---

## Architecture Patterns

### Pattern 1: Durable Workflow

Sequential steps with retries, DLQ, and progress tracking.

```python
# Durable workflow pattern
@worker.function("workflow::process-order")
def process_order(order):
    """Multi-step workflow with tracking."""
    
    # Step 1: Validate
    result = worker.call("orders::validate", order)
    if not result["valid"]:
        return {"status": "failed", "error": "Validation failed"}
    
    # Track progress
    worker.call("state::update", {
        "scope": "orders",
        "key": order["id"],
        "ops": [{"op": "set", "path": "/steps/validate", "value": "done"}]
    })
    
    # Step 2: Charge (async via queue)
    worker.trigger({
        "function_id": "orders::charge",
        "payload": order,
        "action": {"type": "enqueue", "queue": "order-payment"}
    })
    
    return {"status": "processing", "order_id": order["id"]}

# Payment worker
@worker.function("orders::charge")
def charge_order(order):
    """Charge payment."""
    result = process_payment(order)
    
    # Track progress
    worker.call("state::update", {
        "scope": "orders",
        "key": order["id"],
        "ops": [{"op": "set", "path": "/steps/payment", "value": "done"}]
    })
    
    # Step 3: Ship (async via queue)
    worker.trigger({
        "function_id": "orders::ship",
        "payload": order,
        "action": {"type": "enqueue", "queue": "order-shipping"}
    })
```

### Pattern 2: Reactive Backend

Keep views, metrics, or clients in sync automatically.

```python
# Reactive pattern - auto-sync on state change
@worker.trigger(type="state", scope="todos")
def on_todo_change(event):
    """Auto-sync when todo changes."""
    
    # Update live view
    worker.trigger({
        "function_id": "stream::send",
        "payload": {
            "stream_name": "todos-live",
            "data": event["new_value"]
        }
    })
    
    # Update metrics
    worker.trigger({
        "function_id": "metrics::increment",
        "payload": {"metric": "todos.updated"}
    })

# State changes automatically trigger side effects
@worker.function("todos::update")
def update_todo(todo_id, data):
    """Update todo - triggers reactive handlers."""
    current = worker.call("state::get", {"scope": "todos", "key": todo_id})
    updated = {**current, **data}
    
    worker.call("state::set", {
        "scope": "todos",
        "key": todo_id,
        "value": updated
    })
    # Triggers automatically!
```

### Pattern 3: Agentic Backend

Specialized agents hand work to each other.

```python
# Agentic pattern - specialist agents
@worker.function("agents::researcher")
def researcher_agent(task):
    """Research agent - finds information."""
    
    # Store findings in shared state
    worker.call("state::set", {
        "scope": "research",
        "key": task["id"],
        "value": {"findings": [], "status": "in_progress"}
    })
    
    # Do research
    findings = search_and_analyze(task["query"])
    
    # Update state
    worker.call("state::update", {
        "scope": "research",
        "key": task["id"],
        "ops": [
            {"op": "set", "path": "/findings", "value": findings},
            {"op": "set", "path": "/status", "value": "complete"}
        ]
    })
    
    # Hand off to critic
    worker.trigger({
        "function_id": "agents::critic",
        "payload": task,
        "action": {"type": "enqueue", "queue": "agent-tasks"}
    })

@worker.function("agents::critic")
def critic_agent(task):
    """Critic agent - reviews work."""
    
    # Get research findings
    research = worker.call("state::get", {
        "scope": "research",
        "key": task["id"]
    })
    
    # Critique
    critique = analyze_quality(research["findings"])
    
    # Store critique
    worker.call("state::update", {
        "scope": "research",
        "key": task["id"],
        "ops": [{"op": "set", "path": "/critique", "value": critique}]
    })
    
    # Hand off to writer
    worker.trigger({
        "function_id": "agents::writer",
        "payload": task,
        "action": {"type": "enqueue", "queue": "agent-tasks"}
    })
```

### Pattern 4: Event-Driven CQRS

Commands publish events, projections update independently.

```python
# Command side
@worker.function("cmd::add-item")
def add_inventory_item(input):
    """Command: add item to inventory."""
    
    # Validate
    if input["quantity"] <= 0:
        return {"accepted": False, "error": "Invalid quantity"}
    
    # Publish event
    event = {
        "type": "inventory.item-added",
        "item_id": input["item_id"],
        "quantity": input["quantity"],
        "timestamp": time.time()
    }
    
    # Store event
    worker.call("state::set", {
        "scope": "inventory-events",
        "key": f"{event['timestamp']}-{input['item_id']}",
        "value": event
    })
    
    # Publish to subscribers
    worker.trigger({
        "function_id": "pubsub::publish",
        "payload": {"topic": event["type"], "data": event}
    })
    
    return {"accepted": True}

# Query side (projection)
@worker.trigger(type="subscribe", topic="inventory.item-added")
def update_inventory_projection(event):
    """Subscribe to events, update query-optimized state."""
    
    # Get current inventory
    current = worker.call("state::get", {
        "scope": "inventory",
        "key": event["item_id"]
    }) or {"item_id": event["item_id"], "quantity": 0}
    
    # Update
    new_quantity = current["quantity"] + event["quantity"]
    
    worker.call("state::set", {
        "scope": "inventory",
        "key": event["item_id"],
        "value": {**current, "quantity": new_quantity}
    })
```

### Pattern 5: Effect Pipeline

Pure, traceable composition of small functions.

```python
# Effect pipeline - synchronous composition
@worker.function("pipeline::process-data")
def process_data_pipeline(data):
    """Pure composition of small functions."""
    
    # Step 1: Validate
    validated = worker.trigger({
        "function_id": "data::validate",
        "payload": data
    })
    
    # Step 2: Transform
    transformed = worker.trigger({
        "function_id": "data::transform",
        "payload": validated
    })
    
    # Step 3: Enrich
    enriched = worker.trigger({
        "function_id": "data::enrich",
        "payload": transformed
    })
    
    # Step 4: Store
    worker.trigger({
        "function_id": "data::store",
        "payload": enriched
    })
    
    return enriched
```

### Pattern 6: Automation Chain

Webhook/cron automation chains.

```python
# Automation chain pattern
@worker.trigger(type="cron", schedule="0 * * * *")
def hourly_sync():
    """Hourly data sync automation."""
    
    # Step 1: Fetch
    data = worker.trigger({
        "function_id": "external::fetch",
        "payload": {"source": "api"}
    })
    
    # Step 2: Transform
    transformed = worker.trigger({
        "function_id": "data::transform",
        "payload": data
    })
    
    # Step 3: Load
    worker.trigger({
        "function_id": "database::bulk_insert",
        "payload": transformed,
        "action": {"type": "enqueue", "queue": "data-loading"}
    })

# Webhook trigger
@worker.trigger(type="webhook", path="/github/push")
def handle_github_push(request):
    """Handle GitHub webhook."""
    
    # Process push event
    worker.trigger({
        "function_id": "ci::trigger-build",
        "payload": request.data,
        "action": {"type": "enqueue", "queue": "ci-pipeline"}
    })
    
    return {"received": True}
```

---

## Selection Rules

| Requirement | Pattern | Use Case |
|-------------|---------|----------|
| Sequential work with retries | Durable Workflow | Order processing, multi-step operations |
| Keep views in sync | Reactive Backend | Live updates, metrics, cache |
| Specialized agents | Agentic Backend | AI pipelines, task delegation |
| Commands + projections | Event-Driven CQRS | Audit logs, read optimization |
| Pure composition | Effect Pipeline | Data processing, transforms |
| Webhook/cron chains | Automation Chain | Integrations, scheduled tasks |

---

## Agent Discovery

Agents can discover and call functions dynamically.

```python
# Agent discovers available functions
@worker.function("agent::discover")
def discover_capabilities():
    """List all available functions."""
    
    # Get all registered functions
    functions = worker.list_functions()
    
    return {
        "functions": [
            {
                "id": f["id"],
                "description": f["description"],
                "input_schema": f["input_schema"]
            }
            for f in functions
        ]
    }

# Agent calls function dynamically
@worker.function("agent::execute")
def execute_task(task):
    """Execute a task by calling appropriate function."""
    
    # Discover capabilities
    capabilities = worker.call("agent::discover", {})
    
    # Find matching function
    matching = [
        f for f in capabilities["functions"]
        if task["type"] in f["id"]
    ]
    
    if not matching:
        return {"error": "No matching function found"}
    
    # Call the function
    result = worker.call(matching[0]["id"], task["input"])
    
    return {"result": result, "function_used": matching[0]["id"]}
```

---

## Live Catalog Pattern

All services register with a central catalog for discovery.

```python
# Service registration
@worker.function("catalog::register")
def register_service(service_info):
    """Register a new service in the catalog."""
    
    worker.call("state::set", {
        "scope": "catalog",
        "key": service_info["name"],
        "value": {
            "name": service_info["name"],
            "functions": service_info["functions"],
            "endpoints": service_info["endpoints"],
            "registered_at": time.time()
        }
    })
    
    # Notify other services
    worker.trigger({
        "function_id": "pubsub::publish",
        "payload": {
            "topic": "catalog.service-registered",
            "data": service_info
        }
    })

# Service discovery
@worker.function("catalog::discover")
def discover_services(query=None):
    """Discover available services."""
    
    services = worker.call("state::list", {"scope": "catalog"})
    
    if query:
        services = [
            s for s in services
            if query.lower() in s["name"].lower()
            or any(query.lower() in f["id"].lower() for f in s["functions"])
        ]
    
    return services
```

---

## Anti-Patterns

| Pattern | Problem |
|---------|---------|
| Tight coupling | Services depend on each other's internals |
| No idempotency | Retries cause duplicate work |
| Missing error handling | Failures cascade |
| No observability | Can't debug issues |
| Over-engineering | Complex for simple use cases |
| No state management | Lost context between calls |

---

## Integration with Skills

### design-patterns
- **Observer:** State triggers are reactive patterns
- **Strategy:** Choose trigger type based on requirements
- **Facade:** Workers provide simplified interfaces
- **Chain of Responsibility:** Pipelines chain functions

### ddd-development
- **Aggregates:** Workers can manage aggregates
- **Domain Events:** Triggers for event-driven patterns
- **Repositories:** State functions as repositories

### pd
- Reference patterns in Phase 2 (Planning)
- Use triggers for Phase 5 (Testing)
- Observability in Phase 6 (Validation)

---

## Quick Reference

```
┌─────────────────────────────────────────────────────────────┐
│              SERVICE COMPOSITION PRIMITIVES                   │
├─────────────────────────────────────────────────────────────┤
│ WORKER     → Process that registers functions/triggers       │
│ FUNCTION   → Unit of work with stable ID                    │
│ TRIGGER    → What causes function to run                    │
├─────────────────────────────────────────────────────────────┤
│ TRIGGER TYPES                                               │
│ ├─ HTTP     → REST endpoints                                │
│ ├─ Cron     → Scheduled tasks                               │
│ ├─ Queue    → Async processing                              │
│ ├─ State    → Reactive to changes                           │
│ ├─ Stream   → Real-time events                              │
│ ├─ Subscribe → Event listeners                              │
│ └─ Webhook  → External integrations                         │
├─────────────────────────────────────────────────────────────┤
│ ARCHITECTURE PATTERNS                                       │
│ ├─ Durable Workflow      → Multi-step with retries          │
│ ├─ Reactive Backend      → Auto-sync on changes             │
│ ├─ Agentic Backend       → Specialist agents                │
│ ├─ Event-Driven CQRS     → Commands + projections           │
│ ├─ Effect Pipeline       → Pure composition                 │
│ └─ Automation Chain      → Webhook/cron automation          │
└─────────────────────────────────────────────────────────────┘
```

---

## References
- Workers Catalog: https://workers.iii.dev/

## Related Skills

- **design-patterns** — Strategy, Observer, and Factory patterns are used in service composition for routing and event handling.
- **monitoring-observability** — Logging, metrics, and tracing across distributed service compositions.
- **deployment-patterns** — CI/CD and deployment strategies for shipping composed services.
- **pd** — Master orchestrator. Service composition patterns are designed during architecture phases.

- iii Framework: https://github.com/iii-hq/iii
- iii Architecture Patterns: https://github.com/iii-hq/iii/tree/main/skills/iii-architecture-patterns
