---
name: database-patterns
description: "Database patterns — migrations, indexing, N+1 prevention, connection pooling, transactions, repository pattern, CQRS, soft delete, audit trails, and query optimization. Use when designing or working with database layers."
version: 1.0.0
license: MIT
metadata:
  hermes:
    tags: [database, sql, migrations, indexing, transactions, repository-pattern, cqrs]
    related_skills: [ddd-development, clean-code, pd, design-patterns]
---

# Database Patterns

## Overview

Database design directly impacts application performance, data integrity, and maintainability. This skill covers the essential patterns for working with relational databases — from schema migrations to query optimization to architectural patterns like CQRS.

**Core principle:** The database is not just storage. It's a system that enforces constraints, maintains integrity, and serves as the single source of truth. Design it deliberately.

## When to Use

- Designing a new database schema
- Writing or reviewing migrations
- Optimizing slow queries
- Implementing repository or data access layers
- Setting up connection pooling
- Choosing between soft and hard delete
- Adding audit trails to existing systems

**Don't use for:**
- Simple key-value storage (use Redis)
- Document-oriented data without relations (use MongoDB)
- In-memory caching (use Redis/Memcached directly)

---

## I. Migration Strategies

### Migration Rules

| # | Rule | Rationale |
|---|------|-----------|
| 1 | **Every schema change gets a migration** | Reproducible, auditable, reversible |
| 2 | **Migrations must be backward-compatible** | Zero-downtime deployments |
| 3 | **Never modify a deployed migration** | History is immutable |
| 4 | **Name migrations descriptively** | `add_email_index_to_users`, not `migration_42` |
| 5 | **Test migrations up AND down** | Rollback must work |
| 6 | **Separate data migrations from schema migrations** | Different rollback semantics |

### Backward-Compatible Migration Pattern

```sql
-- Step 1: Add new column (nullable or with default)
ALTER TABLE users ADD COLUMN email_normalized VARCHAR(255);

-- Step 2: Backfill existing data (separate migration)
UPDATE users SET email_normalized = LOWER(email) WHERE email_normalized IS NULL;

-- Step 3: Add NOT NULL constraint (only after backfill)
ALTER TABLE users ALTER COLUMN email_normalized SET NOT NULL;

-- Step 4: Add unique constraint (only after data is clean)
ALTER TABLE users ADD CONSTRAINT uq_users_email_normalized UNIQUE (email_normalized);
```

### Migration Decision Tree

```
What kind of change?
  → Add column → Add as nullable first, backfill, then constrain
  → Remove column → Stop using in code first, then drop (after deploy)
  → Rename column → Add new column, copy data, update code, drop old
  → Change type → Create new column, migrate data, swap
  → Add index → CREATE INDEX CONCURRENTLY (non-blocking)
  → Add constraint → Validate existing data first, then add constraint

Is this a destructive change?
  → YES → Requires multi-step migration:
    1. Add new structure
    2. Migrate code to use new structure
    3. Deploy
    4. Remove old structure (next release)
  → NO → Single migration is fine
```

### Migration Example (Alembic/SQLAlchemy)

```python
# alembic/versions/004_add_email_normalized.py
"""Add email_normalized column to users"""

revision = "004_add_email_normalized"
down_revision = "003_add_orders_table"

def upgrade():
    # Step 1: Add nullable column
    op.add_column(
        "users",
        sa.Column("email_normalized", sa.String(255), nullable=True),
    )

    # Step 2: Backfill
    op.execute(
        "UPDATE users SET email_normalized = LOWER(email) "
        "WHERE email_normalized IS NULL"
    )

    # Step 3: Add constraints
    op.alter_column(
        "users",
        "email_normalized",
        nullable=False,
    )
    op.create_unique_constraint(
        "uq_users_email_normalized",
        "users",
        ["email_normalized"],
    )

def downgrade():
    op.drop_constraint("uq_users_email_normalized", "users")
    op.drop_column("users", "email_normalized")
```

---

## II. Indexing Patterns

### Index Types Reference

| Type | Use Case | Example |
|------|----------|---------|
| **B-tree** | Equality and range queries | `WHERE status = 'active'` |
| **Hash** | Equality only (faster than B-tree) | `WHERE id = 42` |
| **GIN** | Full-text search, arrays, JSONB | `WHERE tags @> ARRAY['python']` |
| **GiST** | Geometric, range, full-text | `WHERE location @> point(1,1)` |
| **Partial** | Index subset of rows | `WHERE status = 'active'` |
| **Composite** | Multi-column queries | `(user_id, created_at)` |
| **Covering** | Includes all columns needed | Avoids table lookups |

### Indexing Decision Tree

```
Is the column used in WHERE clauses?
  → YES → Consider B-tree index
  → NO ↓

Is the column used in JOIN conditions?
  → YES → Index the foreign key column
  → NO ↓

Is the column used in ORDER BY?
  → YES → Consider composite index with WHERE columns
  → NO ↓

Is the column used in GROUP BY?
  → YES → Consider index on grouped column(s)
  → NO → Probably don't need an index

How selective is the column?
  > 90% unique values → B-tree index is very effective
  < 10% unique values → Consider partial index or composite index
  Gender (M/F) → Partial index is better than full index
```

### Composite Index Order

```sql
-- Query: WHERE status = 'active' AND created_at > '2024-01-01' ORDER BY name

-- Good: matches the query's WHERE + ORDER BY
CREATE INDEX idx_orders_status_created_name
ON orders (status, created_at, name);

-- Bad: wrong order, can't use index for sorting
CREATE INDEX idx_orders_name_status_created
ON orders (name, status, created_at);

-- Rule of thumb: Equality columns first, then range, then sort columns
```

### Partial Index

```sql
-- Only index active users (most queries filter by status = 'active')
CREATE INDEX idx_users_active_email
ON users (email)
WHERE status = 'active';

-- Much smaller than full index, faster for active user lookups
-- Size comparison: 100K active users vs 10M total users
```

### Covering Index

```sql
-- Query: SELECT name, email FROM users WHERE status = 'active'

-- Covering index (includes all needed columns)
CREATE INDEX idx_users_status_covering
ON users (status)
INCLUDE (name, email);

-- PostgreSQL can answer the query entirely from the index
-- No need to look up the actual table rows
```

### Index Anti-Patterns

| Anti-Pattern | Problem | Fix |
|-------------|---------|-----|
| Index on every column | Wastes space, slows writes | Only index columns used in queries |
| Over-indexing | Index maintenance overhead | Remove unused indexes |
| Missing FK indexes | Slow JOIN operations | Always index foreign keys |
| Index on low-selectivity columns | Full index scan worse than table scan | Use partial indexes instead |

---

## III. N+1 Query Detection and Prevention

### What is N+1?

```python
# BAD: N+1 query problem
orders = db.query(Order).all()  # 1 query
for order in orders:
    # N additional queries (one per order!)
    customer = db.query(Customer).filter_by(id=order.customer_id).first()

# Total queries: 1 + N (e.g., 1 + 1000 = 1001 queries!)
```

### Prevention Patterns

```python
# GOOD: Eager loading (SQLAlchemy)
orders = (
    db.query(Order)
    .options(joinedload(Order.customer))  # JOIN
    .all()
)
# Total queries: 1

# GOOD: Subquery loading (for many-to-many)
orders = (
    db.query(Order)
    .options(subqueryload(Order.items))  # Subquery
    .all()
)
# Total queries: 2 (one for orders, one for all items)

# GOOD: Selectin loading (batch loading)
orders = (
    db.query(Order)
    .options(selectinload(Order.customer))  # IN clause
    .all()
)
# Total queries: 2 (one for orders, one for all customers)
```

### Loading Strategy Decision Tree

```
Is the relationship one-to-one or many-to-one?
  → YES → Use joinedload (single JOIN query)
  → NO ↓

Is the relationship one-to-many?
  → YES → Use selectinload (batch with IN clause)
  → NO ↓

Is the relationship many-to-many?
  → YES → Use subqueryload (separate subquery)
  → NO → Use selectinload as default

Is the collection very large (>1000 items)?
  → YES → Use pagination instead of loading all
  → NO → Use selectinload or subqueryload
```

### Detection Tools

```python
# Django: Enable query logging
import logging
logging.getLogger('django.db.backends').setLevel(logging.DEBUG)

# SQLAlchemy: Echo mode
engine = create_engine(url, echo=True)

# Django: django-debug-toolbar (shows N+1 in UI)
# Python: django-silk (profiling)
# Node.js: pg-monitor, knex-explain
```

---

## IV. Connection Pooling

### Why Connection Pooling?

Database connections are expensive:
- TCP handshake
- Authentication
- SSL negotiation (if enabled)
- Memory allocation on server

Creating a new connection per request: ~50-100ms overhead
Pool with 20 connections: ~0ms overhead (reuse)

### Configuration Guide

```python
# SQLAlchemy connection pool configuration
from sqlalchemy import create_engine

engine = create_engine(
    "postgresql://user:pass@host/db",

    # Pool size: number of persistent connections
    pool_size=20,

    # Max overflow: temporary connections above pool_size
    max_overflow=10,

    # Total max connections: pool_size + max_overflow = 30

    # Connection timeout (seconds)
    pool_timeout=30,

    # Recycle connections after this many seconds
    # (prevents stale connections from load balancers)
    pool_recycle=3600,

    # Pre-ping: verify connection is alive before using
    pool_pre_ping=True,

    # Queue timeout: how long to wait for a connection
    pool_timeout=30,
)
```

### Pool Size Decision Tree

```
What is your database?
  → PostgreSQL → Max connections = ~100-300 (depends on RAM)
  → MySQL → Max connections = ~100-500 (depends on config)
  → SQLite → No pooling needed (file-based)

How many application instances?
  → 1 instance → pool_size = 20, max_overflow = 10
  → 4 instances → pool_size = 10, max_overflow = 5 (each)
  → 10 instances → pool_size = 5, max_overflow = 3 (each)

Rule: pool_size × instances ≤ database max_connections × 0.8
```

### Monitoring Pool Health

```python
from sqlalchemy import event

@event.listens_for(engine, "checkout")
def ping_connection(dbapi_connection, connection_rec, connection_proxy):
    """Verify connection is alive before using."""
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("SELECT 1")
    except Exception:
        # Connection is dead, let pool create a new one
        raise
    finally:
        cursor.close()
```

---

## V. Transaction Patterns

### Isolation Levels

| Level | Dirty Read | Non-Repeatable Read | Phantom Read | Performance |
|-------|-----------|-------------------|-------------|-------------|
| **Read Uncommitted** | Yes | Yes | Yes | Fastest |
| **Read Committed** | No | Yes | Yes | Fast |
| **Repeatable Read** | No | No | Yes* | Moderate |
| **Serializable** | No | No | No | Slowest |

*Phantom reads possible in MySQL/PostgreSQL Repeatable Read depending on implementation.

### Transaction Decision Tree

```
Do you need strict consistency?
  → YES → Serializable isolation
  → NO ↓

Are you reading and writing the same rows?
  → YES → Repeatable Read (prevents non-repeatable reads)
  → NO ↓

Are you doing read-only queries?
  → YES → Read Committed (default, good enough)
  → NO → Read Committed with explicit locks where needed

Is this a long-running report?
  → YES → Use a read replica (don't hold locks on primary)
  → NO → Use the default isolation level
```

### Savepoints for Partial Rollback

```python
async def process_order(order_id: int):
    async with db.begin():
        # Main transaction
        order = await db.get(Order, order_id)
        order.status = "processing"

        try:
            async with db.begin_nested():  # Savepoint
                # Sub-operation that might fail
                await reserve_inventory(order.items)
        except InventoryError:
            # Only the savepoint is rolled back
            # Main transaction continues
            order.status = "inventory_check_needed"

        # Continue with main transaction
        await notify_warehouse(order)
```

### Optimistic Locking

```python
from sqlalchemy import Column, Integer, DateTime
from sqlalchemy.orm import declarative_base
from datetime import datetime

class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True)
    version = Column(Integer, default=0)  # Optimistic lock
    updated_at = Column(DateTime, default=datetime.utcnow)

async def update_order(order_id: int, new_status: str):
    async with db.begin():
        order = await db.get(Order, order_id)
        original_version = order.version

        order.status = new_status
        order.version += 1
        order.updated_at = datetime.utcnow()

        result = await db.execute(
            update(Order)
            .where(Order.id == order_id, Order.version == original_version)
            .values(status=new_status, version=original_version + 1)
        )

        if result.rowcount == 0:
            raise ConflictError("Order was modified by another user")
```

---

## VI. Repository Pattern

### What is Repository Pattern?

The Repository pattern encapsulates data access logic behind an interface, separating the domain model from the persistence mechanism.

```python
from abc import ABC, abstractmethod

# Domain Model
class Order:
    def __init__(self, id: int, status: str, total: float):
        self.id = id
        self.status = status
        self.total = total

    def cancel(self):
        if self.status == "shipped":
            raise ValueError("Cannot cancel shipped order")
        self.status = "cancelled"

# Repository Interface
class OrderRepository(ABC):
    @abstractmethod
    async def find_by_id(self, order_id: int) -> Order | None:
        ...

    @abstractmethod
    async def find_by_customer(self, customer_id: int) -> list[Order]:
        ...

    @abstractmethod
    async def save(self, order: Order) -> None:
        ...

    @abstractmethod
    async def delete(self, order_id: int) -> None:
        ...

# Concrete Implementation
class PostgresOrderRepository(OrderRepository):
    def __init__(self, session):
        self.session = session

    async def find_by_id(self, order_id: int) -> Order | None:
        result = await self.session.execute(
            select(OrderModel).where(OrderModel.id == order_id)
        )
        model = result.scalar_one_or_none()
        return self._to_domain(model) if model else None

    async def save(self, order: Order) -> None:
        model = self._to_model(order)
        await self.session.merge(model)
        await self.session.flush()

    def _to_domain(self, model) -> Order:
        return Order(id=model.id, status=model.status, total=model.total)

    def _to_model(self, order: Order) -> OrderModel:
        return OrderModel(id=order.id, status=order.status, total=order.total)
```

### Repository Decision Tree

```
Are you using DDD (Domain-Driven Design)?
  → YES → Repository pattern is essential
  → NO ↓

Do you have multiple data sources?
  → YES → Repository abstracts the data source
  → NO ↓

Do you need to test without a real database?
  → YES → Repository enables in-memory testing
  → NO → Direct ORM access might be simpler

Are you building a simple CRUD app?
  → YES → Repository might be overkill (use service layer directly)
  → NO → Repository provides clean separation
```

### When NOT to Use Repository

- Simple CRUD applications with 1-2 entities
- Prototypes where speed of development matters
- Scripts or one-off data processing
- When your ORM already provides a clean interface (e.g., SQLAlchemy)

---

## VII. CQRS Basics

### What is CQRS?

Command Query Responsibility Segregation. Separate the read model from the write model.

```
Traditional:  Client → Application → Database (same model for reads and writes)
CQRS:         Client → Commands → Write Database
              Client ← Queries ← Read Database (denormalized, optimized for reads)
```

### When to Use CQRS

| Factor | Monolith CRUD | CQRS |
|--------|--------------|------|
| Read/write ratio | Balanced (1:1 to 10:1) | Highly skewed (100:1+) |
| Read complexity | Simple queries | Complex aggregations, joins |
| Write complexity | Simple CRUD | Complex business logic |
| Scale requirements | Single database handles both | Reads and writes need different scaling |
| Team size | Small | Large, separate read/write teams |

### CQRS Decision Tree

```
Are reads and writes fundamentally different?
  → YES → CQRS is beneficial
  → NO ↓

Do you need to scale reads and writes independently?
  → YES → CQRS enables independent scaling
  → NO ↓

Is the read model significantly different from the write model?
  → YES → CQRS reduces complexity
  → NO → Stick with single model

Is your team large enough to maintain two models?
  → YES → CQRS is manageable
  → NO → Single model is simpler
```

### CQRS Implementation Pattern

```python
# Write Side (Command)
class CreateOrderCommand:
    customer_id: int
    items: list[OrderItem]

class CreateOrderHandler:
    def __init__(self, order_repo: OrderRepository):
        self.order_repo = order_repo

    async def handle(self, command: CreateOrderCommand) -> Order:
        order = Order.create(customer_id=command.customer_id)
        for item in command.items:
            order.add_item(item)
        await self.order_repo.save(order)
        return order

# Read Side (Query)
class OrderSummaryQuery:
    customer_id: int
    status: str | None = None

class OrderSummaryHandler:
    def __init__(self, read_db):
        self.read_db = read_db  # Denormalized read database

    async def handle(self, query: OrderSummaryQuery) -> list[OrderSummary]:
        sql = """
            SELECT id, customer_name, status, total, item_count
            FROM order_summaries
            WHERE customer_id = :customer_id
        """
        params = {"customer_id": query.customer_id}
        if query.status:
            sql += " AND status = :status"
            params["status"] = query.status

        result = await self.read_db.execute(sql, params)
        return [OrderSummary(**row) for row in result]
```

### Synchronization Patterns

```
Write DB → Event → Read DB

Pattern 1: Synchronous (simple but coupled)
  Write to DB, then immediately update read DB
  Pro: Simple, immediate consistency
  Con: Slow, tightly coupled

Pattern 2: Async Event (recommended)
  Write to DB, publish event, event handler updates read DB
  Pro: Decoupled, eventually consistent
  Con: Eventual consistency, more complex

Pattern 3: Change Data Capture (CDC)
  Write to DB, Debezium captures changes, updates read DB
  Pro: No application code changes for sync
  Con: Infrastructure complexity
```

---

## VIII. Soft Delete vs Hard Delete

### Decision Tree

```
Do you need audit trails?
  → YES → Soft delete (preserve record)
  → NO ↓

Is the data legally required to be retained?
  → YES → Soft delete
  → NO ↓

Is the data large and rarely accessed?
  → YES → Hard delete (or archive then hard delete)
  → NO ↓

Do other tables reference this record?
  → YES → Soft delete (preserve referential integrity)
  → NO → Either approach works

Is this a temporary record (cache, session)?
  → YES → Hard delete
  → NO → Soft delete is safer default
```

### Soft Delete Implementation

```sql
-- Add soft delete columns
ALTER TABLE users ADD COLUMN deleted_at TIMESTAMP NULL;
ALTER TABLE users ADD COLUMN deleted_by INTEGER NULL;

-- Create partial index (excluding deleted records)
CREATE INDEX idx_users_active ON users (email) WHERE deleted_at IS NULL;

-- Query only active users (automatic with view)
CREATE VIEW active_users AS
SELECT * FROM users WHERE deleted_at IS NULL;
```

```python
# SQLAlchemy soft delete mixin
from sqlalchemy import Column, DateTime, func

class SoftDeleteMixin:
    deleted_at = Column(DateTime, nullable=True)
    deleted_by = Column(Integer, nullable=True)

    def soft_delete(self, user_id: int):
        self.deleted_at = func.now()
        self.deleted_by = user_id

    def restore(self):
        self.deleted_at = None
        self.deleted_by = None

    @hybrid_property
    def is_deleted(self):
        return self.deleted_at is not None

# Base query filter
class UserQuery:
    def active(self):
        return self.filter(User.deleted_at.is_(None))

    def including_deleted(self):
        return self  # No filter
```

### Archive Pattern (Soft Delete + Archival)

```python
# Step 1: Soft delete
user.soft_delete(user_id=current_user.id)

# Step 2: Schedule archival (after 90 days)
# In cron job or background task:
old_deleted_users = (
    session.query(User)
    .filter(User.deleted_at < datetime.utcnow() - timedelta(days=90))
    .all()
)

for user in old_deleted_users:
    # Archive to separate table or export to cold storage
    archive_user(user)
    # Then hard delete from main table
    session.delete(user)
```

---

## IX. Audit Trail Patterns

### What to Audit

| Event Type | What to Record | When |
|-----------|---------------|------|
| **Create** | Full record, who created | On insert |
| **Update** | Changed fields (before/after), who updated | On update |
| **Delete** | Full record, who deleted | On delete |
| **Access** | Who accessed, when | On sensitive reads |
| **Login** | IP, user agent, success/failure | On auth events |

### Audit Table Design

```sql
CREATE TABLE audit_log (
    id BIGSERIAL PRIMARY KEY,
    table_name VARCHAR(100) NOT NULL,
    record_id INTEGER NOT NULL,
    action VARCHAR(10) NOT NULL,  -- INSERT, UPDATE, DELETE
    old_values JSONB,
    new_values JSONB,
    changed_fields TEXT[],
    performed_by INTEGER REFERENCES users(id),
    performed_at TIMESTAMP NOT NULL DEFAULT NOW(),
    ip_address INET,
    user_agent TEXT
);

-- Index for efficient querying
CREATE INDEX idx_audit_log_table_record
ON audit_log (table_name, record_id);

CREATE INDEX idx_audit_log_performed_by
ON audit_log (performed_by);

CREATE INDEX idx_audit_log_performed_at
ON audit_log (performed_at DESC);
```

### Audit Trigger (PostgreSQL)

```sql
-- Generic audit function
CREATE OR REPLACE FUNCTION audit_trigger_func()
RETURNS TRIGGER AS $$
DECLARE
    old_data JSONB;
    new_data JSONB;
    changed_fields TEXT[];
BEGIN
    IF TG_OP = 'DELETE' THEN
        old_data := to_jsonb(OLD);
        INSERT INTO audit_log (table_name, record_id, action, old_values)
        VALUES (TG_TABLE_NAME, OLD.id, 'DELETE', old_data);

    ELSIF TG_OP = 'UPDATE' THEN
        old_data := to_jsonb(OLD);
        new_data := to_jsonb(NEW);

        -- Find changed fields
        SELECT array_agg(key) INTO changed_fields
        FROM jsonb_each(old_data)
        WHERE old_data->>key IS DISTINCT FROM new_data->>key;

        IF changed_fields IS NOT NULL THEN
            INSERT INTO audit_log (table_name, record_id, action, old_values, new_values, changed_fields)
            VALUES (TG_TABLE_NAME, NEW.id, 'UPDATE', old_data, new_data, changed_fields);
        END IF;

    ELSIF TG_OP = 'INSERT' THEN
        new_data := to_jsonb(NEW);
        INSERT INTO audit_log (table_name, record_id, action, new_values)
        VALUES (TG_TABLE_NAME, NEW.id, 'INSERT', new_data);
    END IF;

    RETURN COALESCE(NEW, OLD);
END;
$$ LANGUAGE plpgsql;

-- Apply to table
CREATE TRIGGER audit_users
AFTER INSERT OR UPDATE OR DELETE ON users
FOR EACH ROW EXECUTE FUNCTION audit_trigger_func();
```

---

## X. Query Optimization

### EXPLAIN Analysis

```sql
-- Basic EXPLAIN
EXPLAIN SELECT * FROM orders WHERE customer_id = 42;

-- Detailed EXPLAIN with costs
EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
SELECT * FROM orders WHERE customer_id = 42 AND status = 'pending';

-- What to look for:
-- Seq Scan → Missing index (bad for large tables)
-- Index Scan → Good, using index
-- Nested Loop → Good for small result sets
-- Hash Join → Good for larger result sets
-- Sort → Might need index for ORDER BY
-- Buffers: shared hit → Cache hits (good)
-- Buffers: shared read → Disk reads (investigate)
```

### Common Performance Issues

| Issue | Symptom | Fix |
|-------|---------|-----|
| Missing index | Sequential Scan on large table | Add appropriate index |
| N+1 queries | Many similar queries in logs | Eager loading |
| SELECT * | Fetching unnecessary columns | Select only needed columns |
| Large result sets | Slow response, high memory | Pagination, limits |
| Missing WHERE | Full table scan | Add filtering conditions |
| LIKE '%term%' | Can't use index | Full-text search instead |
| OR with different columns | Query planner can't optimize | UNION ALL instead |
| Subquery in WHERE | Correlated subquery per row | JOIN or CTE |

### Query Optimization Checklist

```sql
-- 1. Check for missing indexes
SELECT schemaname, relname, seq_scan, idx_scan
FROM pg_stat_user_tables
WHERE seq_scan > 100
ORDER BY seq_scan DESC;

-- 2. Find unused indexes
SELECT schemaname, relname, indexrelname, idx_scan
FROM pg_stat_user_indexes
WHERE idx_scan = 0
ORDER BY pg_relation_size(indexrelid) DESC;

-- 3. Find slow queries (requires pg_stat_statements)
SELECT query, calls, mean_exec_time, total_exec_time
FROM pg_stat_statements
ORDER BY mean_exec_time DESC
LIMIT 10;

-- 4. Check table bloat
SELECT
    schemaname, tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
FROM pg_tables
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
```

---

## XI. Database Versioning

### Versioning Decision Tree

```
Do you use migrations?
  → YES → You already have versioning (migration numbers)
  → NO → Start with a migration tool

Do you need to support multiple schema versions simultaneously?
  → YES → Use migration-based versioning
  → NO → Simple migration sequence is fine

Is your database shared across services?
  → YES → Each service should have its own schema
  → NO → Single migration sequence is fine

Do you need rollback capability?
  → YES → Every migration needs a downgrade
  → NO → Forward-only migrations (simpler but risky)
```

### Versioning Strategies

```
Strategy 1: Sequential Migrations
  001_create_users.sql
  002_add_email_index.sql
  003_create_orders.sql
  → Simple, linear history

Strategy 2: Timestamped Migrations
  20240115_103000_create_users.sql
  20240115_110000_add_email_index.sql
  → Avoids merge conflicts in teams

Strategy 3: Branch-based Migrations
  main/
    001_create_users.sql
  feature/orders/
    002_create_orders.sql
  → Parallel development, merge when ready
```

---

## XII. Connection Pool Monitoring

### Key Metrics

```python
# SQLAlchemy pool events
from sqlalchemy import event

@event.listens_for(engine, "checkout")
def on_checkout(dbapi_conn, conn_rec, conn_proxy):
    logger.debug(f"Connection checked out. Pool size: {engine.pool.size()}")

@event.listens_for(engine, "checkin")
def on_checkin(dbapi_conn, conn_rec):
    logger.debug(f"Connection returned. Pool checked in.")

@event.listens_for(engine, "connect")
def on_connect(dbapi_conn, conn_record):
    logger.info("New database connection established")

@event.listens_for(engine, "checkout")
def on_checkout(dbapi_conn, conn_rec, conn_proxy):
    if conn_proxy._pool._overflow_count > engine.pool.size() * 0.8:
        logger.warning("Connection pool near capacity!")
```

### Pool Health Dashboard

```
┌─────────────────────────────────────────────┐
│ Database Connection Pool                     │
├─────────────────────────────────────────────┤
│ Active Connections:    15/20 (75%)           │
│ Idle Connections:      5                     │
│ Overflow Connections:  3/10                  │
│ Total Connections:     18/30                 │
│ Wait Time (avg):      12ms                  │
│ Timeout Errors:       0                     │
└─────────────────────────────────────────────┘
```

---

## XIII. Complete Database Checklist

### Schema Design

- [ ] Primary keys defined (integer or UUID)
- [ ] Foreign keys with ON DELETE behavior specified
- [ ] NOT NULL constraints on required fields
- [ ] CHECK constraints for business rules
- [ ] Unique constraints where needed
- [ ] Appropriate data types (VARCHAR vs TEXT, INT vs BIGINT)

### Performance

- [ ] Indexes on foreign keys
- [ ] Indexes on frequently queried columns
- [ ] Composite indexes match query patterns
- [ ] Partial indexes for filtered queries
- [ ] No unnecessary indexes (check unused)
- [ ] Connection pooling configured

### Data Integrity

- [ ] Transactions for multi-step operations
- [ ] Optimistic locking for concurrent updates
- [ ] Audit trail for sensitive data
- [ ] Soft delete where data retention matters
- [ ] Backup strategy tested

### Operations

- [ ] Migrations are backward-compatible
- [ ] Migrations have downgrades
- [ ] Migration testing in CI/CD
- [ ] Database monitoring in place
- [ ] Slow query logging enabled
- [ ] Connection pool monitoring

---

## References

- **Use The Index, Luke** — https://use-the-index-luke.com
- **PostgreSQL Documentation** — https://www.postgresql.org/docs/
- **SQLAlchemy Documentation** — https://docs.sqlalchemy.org/
- **Martin Fowler — Patterns of Enterprise Application Architecture** — Repository, Unit of Work
- ** Vaughn Vernon — Implementing Domain-Driven Design** — Aggregate design, repositories

## Related Skills

- **ddd-development** — Repository pattern and Aggregate design directly map to database schema.
- **clean-code** — Clear naming for queries, migrations, and schema definitions.
- **pd** — Master orchestrator. Database design is part of Phase 1 (Brainstorming) and Phase 2 (Planning).
- **design-patterns** — Repository, Unit of Work, and CQRS patterns for data access.
