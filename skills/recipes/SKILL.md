---
name: recipes
description: "Practical recipes combining multiple skills — create APIs, debug production issues, refactor legacy code, add authentication, set up projects, and optimize performance. Each recipe is a step-by-step guide with exact commands and expected outputs."
version: 1.0.0
license: MIT
metadata:
  hermes:
    tags: [recipes, cookbook, practical, combining-skills, tutorials]
    related_skills: [pd, clean-code, test-driven-development, systematic-debugging, api-design, database-patterns, auth-patterns, security-checklist, monitoring-observability, ddd-development, design-patterns]
---

# Practical Recipes

## Overview

Recipes are step-by-step guides that combine multiple skills to accomplish common development tasks. Each recipe specifies which skills to load, the exact steps to follow, and the expected outcomes.

**Core principle:** No skill works in isolation. Real development requires orchestrating multiple skills together.

## When to Use

- Starting a new project and need a structured approach
- Facing a common task that involves multiple skills
- Wanting to see how skills work together in practice
- Onboarding new developers with practical examples

---

## Recipe 1: Create a REST API

**Goal:** Build a production-ready REST API from scratch.
**Skills to load:** pd, clean-code, api-design, test-driven-development, database-patterns

### Step-by-Step

#### Phase 1: Specification (pd)

```
1. Run brainstorming:
   - What resources does the API expose?
   - Who are the consumers?
   - What are the performance requirements?

2. Create spec structure:
   mkdir -p .spec/{api,database,tests}

3. Write API spec:
   - Resources: /users, /orders, /products
   - Auth: JWT tokens
   - Pagination: Cursor-based for large collections
   - Error format: RFC 7807 Problem Details
```

#### Phase 2: Database Design (database-patterns)

```sql
-- Schema design
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) NOT NULL UNIQUE,
    name VARCHAR(255) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE orders (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    status VARCHAR(50) NOT NULL DEFAULT 'pending',
    total DECIMAL(10,2) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_orders_user_id ON orders(user_id);
CREATE INDEX idx_orders_status ON orders(status) WHERE status != 'cancelled';
```

#### Phase 3: API Implementation (api-design + clean-code)

```python
# app/api/users.py
from fastapi import APIRouter, Depends, HTTPException
from app.models import User, UserCreate
from app.repositories import UserRepository
from app.auth import get_current_user

router = APIRouter(prefix="/users", tags=["users"])

@router.get("", response_model=list[User])
async def list_users(
    cursor: str | None = None,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
):
    """List users with cursor pagination."""
    repo = UserRepository(db)
    return await repo.list(cursor=cursor, limit=min(limit, 100))

@router.post("", response_model=User, status_code=201)
async def create_user(
    user: UserCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a new user."""
    repo = UserRepository(db)
    existing = await repo.find_by_email(user.email)
    if existing:
        raise HTTPException(
            status_code=409,
            detail={"type": "conflict", "title": "Email already exists"},
        )
    return await repo.create(user)

@router.get("/{user_id}", response_model=User)
async def get_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Get user by ID."""
    repo = UserRepository(db)
    user = await repo.find_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user
```

#### Phase 4: Tests (test-driven-development)

```python
# tests/test_users.py
import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_create_user(client: AsyncClient):
    response = await client.post("/users", json={
        "email": "test@example.com",
        "name": "Test User",
    })
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "test@example.com"
    assert "id" in data

@pytest.mark.asyncio
async def test_create_user_duplicate_email(client: AsyncClient):
    await client.post("/users", json={"email": "dup@example.com", "name": "First"})
    response = await client.post("/users", json={"email": "dup@example.com", "name": "Second"})
    assert response.status_code == 409

@pytest.mark.asyncio
async def test_list_users_pagination(client: AsyncClient, db):
    # Create 25 users
    for i in range(25):
        await client.post("/users", json={"email": f"user{i}@test.com", "name": f"User {i}"})

    response = await client.get("/users?limit=10")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 10
```

#### Expected Output

```
✅ API running on http://localhost:8000
✅ OpenAPI docs at http://localhost:8000/docs
✅ All tests passing
✅ Database migrations applied
```

---

## Recipe 2: Debug a Production Issue

**Goal:** Systematically investigate and resolve a production bug.
**Skills to load:** systematic-debugging, monitoring-observability

### Scenario

Users report intermittent 500 errors on the `/orders` endpoint. The errors happen ~5% of requests.

### Step-by-Step

#### Phase 1: Root Cause Investigation (systematic-debugging)

```
1. Gather evidence:
   - Check error rate in Grafana dashboard
   - Search logs for 500 errors in the time range
   - Look at traces for failed requests

2. Form hypothesis:
   - Logs show: "ConnectionResetError: [Errno 104] Connection reset by peer"
   - Traces show: Database calls taking 5-10s before timeout
   - Hypothesis: Database connection pool exhaustion under load

3. Test hypothesis:
   - Check connection pool metrics:
     rate(db_connection_pool_active / db_connection_pool_size[5m])
   - Confirmed: Pool utilization hitting 100% during peak hours
```

#### Phase 2: Investigation (monitoring-observability)

```python
# Check pool configuration
# Current config (in config.py):
DATABASE_POOL_SIZE = 5  # Too small!
DATABASE_MAX_OVERFLOW = 10

# Check query logs for slow queries
# Found: N+1 query in order listing endpoint
# Each order triggers a separate user lookup

# Root cause confirmed:
# 1. N+1 queries creating excessive connections
# 2. Pool size too small for load
# 3. Connection timeouts causing 500 errors
```

#### Phase 3: Fix

```python
# Fix 1: Eliminate N+1 query
# BEFORE
async def list_orders(user_id: int):
    orders = await db.query(Order).filter_by(user_id=user_id).all()
    for order in orders:
        order.user = await db.get(User, order.user_id)  # N+1!
    return orders

# AFTER
async def list_orders(user_id: int):
    orders = (
        await db.query(Order)
        .options(joinedload(Order.user))  # Single JOIN query
        .filter_by(user_id=user_id)
        .all()
    )
    return orders

# Fix 2: Increase pool size
DATABASE_POOL_SIZE = 20
DATABASE_MAX_OVERFLOW = 10
DATABASE_POOL_RECYCLE = 3600
DATABASE_POOL_PRE_PING = True
```

#### Phase 4: Verify

```bash
# Deploy fix
git commit -m "fix: eliminate N+1 query in order listing"
git push

# Monitor after deploy
# Watch error rate in Grafana
# Watch connection pool utilization
# Expected: Error rate drops to 0%, pool utilization stays below 50%
```

#### Expected Output

```
✅ Error rate dropped from 5% to 0%
✅ Connection pool utilization: 35% (was 100%)
✅ P99 latency: 120ms (was 2500ms)
✅ No user-reported errors in 24 hours
```

---

## Recipe 3: Refactor Legacy Code

**Goal:** Improve code quality without breaking functionality.
**Skills to load:** clean-code, ddd-development, requesting-code-review, test-driven-development

### Scenario

Legacy module with 2000-line file, no tests, unclear responsibilities.

### Step-by-Step

#### Phase 1: Safety Net (test-driven-development)

```
1. Add characterization tests:
   - Test current behavior (even if it's wrong)
   - Capture inputs/outputs for all public methods
   - These tests become your safety net

2. Don't refactor without tests — it's guessing
```

```python
# tests/test_legacy_module.py
# Characterization tests (document current behavior)
class TestLegacyModule:
    def test_process_order_with_valid_input(self):
        """Current behavior: returns order dict"""
        result = process_order({"item": "widget", "qty": 5})
        assert result["status"] == "processed"
        assert result["total"] == 25.0

    def test_process_order_with_zero_qty(self):
        """Current behavior: returns error dict"""
        result = process_order({"item": "widget", "qty": 0})
        assert result["status"] == "error"
```

#### Phase 2: Extract Responsibilities (clean-code)

```
1. Identify responsibilities in the monolith:
   - Order validation
   - Price calculation
   - Inventory management
   - Notification sending
   - Database persistence

2. Extract one responsibility at a time:
   - Create new module for each responsibility
   - Move code, update imports
   - Run tests after each extraction
```

```python
# BEFORE: Everything in one file
class OrderProcessor:
    def process(self, order_data):
        # Validation (50 lines)
        # Price calculation (100 lines)
        # Inventory check (80 lines)
        # Database save (60 lines)
        # Email notification (40 lines)
        # Return result
        pass

# AFTER: Separated concerns
# app/orders/validator.py
class OrderValidator:
    def validate(self, order_data) -> ValidationResult: ...

# app/orders/pricing.py
class PriceCalculator:
    def calculate(self, items: list[Item]) -> Decimal: ...

# app/orders/inventory.py
class InventoryManager:
    def check_and_reserve(self, items: list[Item]) -> bool: ...

# app/orders/processor.py
class OrderProcessor:
    def __init__(self, validator, pricing, inventory, notification):
        self.validator = validator
        self.pricing = pricing
        self.inventory = inventory
        self.notification = notification

    def process(self, order_data):
        self.validator.validate(order_data)
        total = self.pricing.calculate(order_data["items"])
        self.inventory.check_and_reserve(order_data["items"])
        # ... persist and notify
```

#### Phase 3: Apply DDD Patterns (ddd-development)

```
1. Identify aggregates:
   - Order (root aggregate)
   - OrderItem (entity within Order)
   - Price (value object)

2. Create domain model:
   - Move business logic into domain objects
   - Keep infrastructure at the edges
```

```python
# app/orders/domain.py
class Order:
    def __init__(self, customer_id: int):
        self.id = None
        self.customer_id = customer_id
        self.items: list[OrderItem] = []
        self.status = OrderStatus.DRAFT

    def add_item(self, product_id: int, quantity: int, price: Decimal):
        if quantity <= 0:
            raise ValueError("Quantity must be positive")
        self.items.append(OrderItem(product_id, quantity, price))

    def calculate_total(self) -> Decimal:
        return sum(item.subtotal for item in self.items)

    def confirm(self):
        if not self.items:
            raise ValueError("Cannot confirm empty order")
        self.status = OrderStatus.CONFIRMED
```

#### Phase 4: Code Review (requesting-code-review)

```
1. Create PR with refactored code
2. Self-review checklist:
   - [ ] All characterization tests still pass
   - [ ] No new tests broken
   - [ ] Each extraction is atomic (one commit per extraction)
   - [ ] No logic changes (only structural changes)
3. Request review focusing on:
   - Are the extracted modules coherent?
   - Is the domain model accurate?
   - Are there any hidden dependencies?
```

#### Expected Output

```
✅ 12 files created (from 1 monolith)
✅ All characterization tests passing
✅ New unit tests added for each module
✅ Code review approved
✅ Deployment successful with 0 regressions
```

---

## Recipe 4: Add Authentication to Existing App

**Goal:** Secure an existing application with JWT authentication.
**Skills to load:** auth-patterns, security-checklist, test-driven-development

### Step-by-Step

#### Phase 1: Security Assessment (security-checklist)

```
1. Check current state:
   - Are any endpoints publicly exposed? → YES
   - Is there any auth at all? → NO
   - What data needs protection? → User data, orders

2. Plan auth strategy:
   - JWT access tokens (15 min expiry)
   - Refresh tokens (7 day expiry)
   - bcrypt password hashing
   - Rate limiting on login endpoint
```

#### Phase 2: Implement Auth (auth-patterns)

```python
# app/auth/service.py
from passlib.context import CryptContext
from jose import JWTError, jwt
from datetime import datetime, timedelta

pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

class AuthService:
    def __init__(self, secret_key: str):
        self.secret_key = secret_key
        self.algorithm = "HS256"

    def hash_password(self, password: str) -> str:
        return pwd_context.hash(password)

    def verify_password(self, password: str, hashed: str) -> bool:
        return pwd_context.verify(password, hashed)

    def create_access_token(self, user_id: int) -> str:
        expire = datetime.utcnow() + timedelta(minutes=15)
        return jwt.encode(
            {"sub": str(user_id), "exp": expire, "type": "access"},
            self.secret_key,
            algorithm=self.algorithm,
        )

    def create_refresh_token(self, user_id: int) -> str:
        expire = datetime.utcnow() + timedelta(days=7)
        return jwt.encode(
            {"sub": str(user_id), "exp": expire, "type": "refresh"},
            self.secret_key,
            algorithm=self.algorithm,
        )

    def verify_token(self, token: str) -> dict | None:
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            return payload
        except JWTError:
            return None
```

```python
# app/auth/dependencies.py
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security = HTTPBearer()

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    auth_service: AuthService = Depends(get_auth_service),
) -> User:
    payload = auth_service.verify_token(credentials.credentials)
    if not payload or payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid token")

    user = await get_user_by_id(int(payload["sub"]))
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user
```

#### Phase 3: Apply to Routes

```python
# Protected endpoint
@router.get("/orders")
async def list_orders(user: User = Depends(get_current_user)):
    return await get_user_orders(user.id)

# Public endpoint (no auth)
@router.post("/login")
async def login(credentials: LoginRequest):
    # ...
```

#### Phase 4: Add Rate Limiting

```python
# app/auth/rate_limit.py
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@router.post("/login")
@limiter.limit("5/minute")  # 5 login attempts per minute per IP
async def login(request: Request, credentials: LoginRequest):
    # ...
```

#### Expected Output

```
✅ Login endpoint: POST /auth/login
✅ Register endpoint: POST /auth/register
✅ Token refresh: POST /auth/refresh
✅ Protected endpoints require Bearer token
✅ Rate limiting: 5 login attempts/minute
✅ All existing tests still pass
✅ New auth tests added
```

---

## Recipe 5: Set Up a New Project

**Goal:** Initialize a well-structured project from scratch.
**Skills to load:** pd, clean-code, database-patterns, monitoring-observability

### Step-by-Step

#### Phase 1: Project Structure (clean-code + pd)

```
my-project/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI app
│   ├── config.py            # Settings
│   ├── models/              # SQLAlchemy models
│   │   ├── __init__.py
│   │   └── user.py
│   ├── api/                 # Route handlers
│   │   ├── __init__.py
│   │   └── users.py
│   ├── services/            # Business logic
│   │   ├── __init__.py
│   │   └── user_service.py
│   ├── repositories/        # Data access
│   │   ├── __init__.py
│   │   └── user_repository.py
│   └── middleware/          # Cross-cutting
│       ├── __init__.py
│       └── logging.py
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   └── test_users.py
├── migrations/              # Alembic
│   ├── env.py
│   └── versions/
├── docker-compose.yml
├── Dockerfile
├── pyproject.toml
├── alembic.ini
└── README.md
```

#### Phase 2: Configuration (clean-code)

```python
# app/config.py
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Application
    APP_NAME: str = "My Project"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False

    # Database
    DATABASE_URL: str = "postgresql://user:pass@localhost:5432/mydb"
    DATABASE_POOL_SIZE: int = 20
    DATABASE_MAX_OVERFLOW: int = 10

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # Auth
    JWT_SECRET: str = ""  # Must be set in environment
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15

    # Monitoring
    LOG_LEVEL: str = "INFO"
    ENABLE_TRACING: bool = False
    JAEGER_URL: str = "http://localhost:14268/api/traces"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = Settings()
```

#### Phase 3: Database Setup (database-patterns)

```python
# app/database.py
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

engine = create_async_engine(
    settings.DATABASE_URL,
    pool_size=settings.DATABASE_POOL_SIZE,
    max_overflow=settings.DATABASE_MAX_OVERFLOW,
    pool_pre_ping=True,
    pool_recycle=3600,
)

AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
```

#### Phase 4: Monitoring Setup (monitoring-observability)

```python
# app/middleware/logging.py
import structlog
import uuid
from fastapi import Request

def setup_logging():
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.BoundLogger,
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
    )

@app.middleware("http")
async def logging_middleware(request: Request, call_next):
    request_id = str(uuid.uuid4())
    structlog.contextvars.bind_contextvars(request_id=request_id)

    response = await call_next(request)

    structlog.contextvars.unbind_contextvars("request_id")
    return response

# Health checks
@app.get("/health/live")
async def liveness():
    return {"status": "healthy"}

@app.get("/health/ready")
async def readiness():
    checks = {}
    try:
        await db.execute("SELECT 1")
        checks["database"] = "healthy"
    except Exception:
        checks["database"] = "unhealthy"

    status = "healthy" if all(v == "healthy" for v in checks.values()) else "unhealthy"
    return {"status": status, "checks": checks}
```

#### Expected Output

```
✅ Project structure created
✅ Configuration loaded from .env
✅ Database connection pooling configured
✅ Structured logging active
✅ Health check endpoints available
✅ Ready for development
```

---

## Recipe 6: Performance Optimization

**Goal:** Identify and fix performance bottlenecks.
**Skills to load:** monitoring-observability, database-patterns, clean-code

### Step-by-Step

#### Phase 1: Measure (monitoring-observability)

```bash
# 1. Check current metrics
# - P99 latency: 2.5s (target: <500ms)
# - Error rate: 0.1% (acceptable)
# - Throughput: 100 req/s (target: 500 req/s)

# 2. Find slow endpoints
# Prometheus query:
topk(10, histogram_quantile(0.99, rate(http_request_duration_seconds_bucket[5m])))

# Results:
# /orders: P99 = 4.5s
# /products: P99 = 1.2s
# /users: P99 = 200ms

# 3. Check traces for /orders
# Found: 3 database queries per order (N+1)
# Found: Full table scan on orders table (missing index)
```

#### Phase 2: Fix Database Issues (database-patterns)

```sql
-- Add missing index
CREATE INDEX idx_orders_user_status
ON orders (user_id, status)
WHERE status != 'cancelled';

-- Analyze slow query
EXPLAIN ANALYZE
SELECT o.*, u.name, u.email
FROM orders o
JOIN users u ON u.id = o.user_id
WHERE o.user_id = 42;

-- Before: Seq Scan on orders (1.2s)
-- After: Index Scan on orders (12ms)
```

#### Phase 3: Fix Application Issues (clean-code)

```python
# BEFORE: N+1 queries
async def get_orders_with_details(user_id: int):
    orders = await db.query(Order).filter_by(user_id=user_id).all()
    result = []
    for order in orders:
        user = await db.get(User, order.user_id)  # N+1!
        items = await db.query(OrderItem).filter_by(order_id=order.id).all()  # N+1!
        result.append({"order": order, "user": user, "items": items})
    return result

# AFTER: Optimized queries
async def get_orders_with_details(user_id: int):
    orders = (
        await db.query(Order)
        .options(
            joinedload(Order.user),
            selectinload(Order.items),
        )
        .filter(Order.user_id == user_id)
        .all()
    )
    return orders

# Additional: Add caching
from app.cache import cache

@cache(ttl=300)  # Cache for 5 minutes
async def get_orders_with_details(user_id: int):
    # ... optimized query ...
```

#### Phase 4: Verify Improvement

```bash
# After deploying fixes:
# P99 latency: 180ms (was 4.5s) ✅
# Throughput: 450 req/s (was 100 req/s) ✅
# Error rate: 0.05% (improved) ✅
```

#### Expected Output

```
✅ P99 latency: 180ms (was 4.5s)
✅ Throughput: 450 req/s (was 100 req/s)
✅ Database queries per request: 2 (was 200+)
✅ All tests passing
✅ Monitoring confirms improvement
```

---

## Recipe Quick Reference

| Recipe | Skills Used | Key Outcome |
|--------|------------|-------------|
| Create REST API | pd, api-design, tdd, database-patterns, clean-code | Production-ready API |
| Debug Production Issue | systematic-debugging, monitoring-observability | Root cause found and fixed |
| Refactor Legacy Code | clean-code, ddd, tdd, requesting-code-review | Code quality improved |
| Add Authentication | auth-patterns, security-checklist, tdd | Secure endpoints |
| Set Up New Project | pd, clean-code, database-patterns, monitoring-observability | Structured project |
| Performance Optimization | monitoring-observability, database-patterns, clean-code | Measurable improvement |

---

## References

- **Project Development (PD)** — Orchestration skill for full pipeline
- **Clean Code** — Code quality standards
- **Test-Driven Development** — Testing methodology
- **Systematic Debugging** — Root cause analysis
- **API Design** — REST API patterns
- **Database Patterns** — Data layer patterns
- **Auth Patterns** — Authentication/authorization
- **Security Checklist** — Security requirements
- **Monitoring & Observability** — Production visibility

## Related Skills

- **pd** — Master orchestrator. Recipes combine multiple PD pipeline skills.
- **clean-code** — Code quality principles applied in each recipe.
- **test-driven-development** — TDD discipline in implementation recipes.
- **systematic-debugging** — Debugging recipes for production issues.
- **api-design** — API creation and design recipes.
- **database-patterns** — Database setup and optimization recipes.
- **auth-patterns** — Authentication implementation recipes.
- **security-checklist** — Security audit recipes.
- **monitoring-observability** — Observability setup recipes.
- **ddd-development** — Domain modeling recipes.
- **design-patterns** — Pattern application recipes.
