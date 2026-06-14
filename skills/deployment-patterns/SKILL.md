---
name: deployment-patterns
description: "Deployment patterns — blue-green, canary, rolling updates, feature flags, CI/CD, container orchestration. Use when designing deployment pipelines, release strategies, or production operations."
version: 1.0.0
author: ISIS
license: MIT
metadata:
  hermes:
    tags: [deployment, ci-cd, docker, kubernetes, feature-flags, release]
    related_skills: [service-composition, monitoring-observability, clean-code, pd]
---

# Deployment Patterns

## Overview

Deployment is the bridge between code and users. A good deployment strategy minimizes risk, enables fast iteration, and provides quick rollback when things go wrong. The goal: deploy frequently, confidently, and safely.

**Core principle:** If you can't roll back in 5 minutes, you're not ready to deploy.

## When to Use

- Setting up CI/CD pipelines
- Designing release strategies
- Implementing feature flags
- Planning database migrations
- Setting up container orchestration
- Managing multiple environments

**Don't over-engineer:**
- Single-developer projects (simple deploy is fine)
- Internal tools (low risk tolerance needed)
- Prototypes (just ship it)

---

## I. Blue-Green Deployments

### Concept

Two identical production environments. Only one serves traffic at a time.

```
                    ┌─────────────┐
                    │   Load      │
    Users ────────► │   Balancer  │
                    └──────┬──────┘
                           │
                    ┌──────┴──────┐
                    │             │
               ┌────▼────┐  ┌────▼────┐
               │  BLUE   │  │  GREEN  │
               │ (active)│  │ (idle)  │
               └─────────┘  └─────────┘
```

### Implementation

```yaml
# docker-compose.yml — Blue-Green
version: '3.8'
services:
  blue:
    image: app:v1.0
    environment:
      - COLOR=blue
    ports:
      - "8001:8000"
  
  green:
    image: app:v1.1
    environment:
      - COLOR=green
    ports:
      - "8002:8000"

  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
```

```bash
# Switch traffic from blue to green
# 1. Deploy new version to green
docker-compose up -d green

# 2. Run health checks on green
curl -f http://localhost:8002/health || exit 1

# 3. Update nginx to point to green
sed -i 's/blue:8000/green:8000/' nginx.conf
docker-compose exec nginx nginx -s reload

# 4. Keep blue running for quick rollback
# If issues: switch back to blue in seconds
```

### When to Use

- Zero-downtime deploys required
- Quick rollback needed (< 1 minute)
- Database changes are backward-compatible
- You have resources for two full environments

---

## II. Canary Releases

### Concept

Deploy to a small subset of users first. Monitor, then gradually increase.

```
                    ┌─────────────┐
                    │   Load      │
    Users ────────► │   Balancer  │
                    └──────┬──────┘
                           │
                    ┌──────┴──────┐
                    │             │
               ┌────▼────┐  ┌────▼────┐
               │ CURRENT │  │ CANARY  │
               │  (95%)  │  │  (5%)   │
               └─────────┘  └─────────┘
```

### Implementation

```nginx
# Nginx — Canary routing
upstream backend {
    server current:8000 weight=19;  # 95%
    server canary:8000 weight=1;    # 5%
}

# Or by header
map $http_x_canary $backend {
    "true"  canary_backend;
    default current_backend;
}
```

```python
# Application-level canary
import random

def route_to_canary(user_id: int, canary_percent: float = 0.05) -> bool:
    """Deterministic canary routing based on user ID."""
    return hash(user_id) % 100 < canary_percent * 100

# In request handler
if route_to_canary(user_id):
    return call_canary_service(request)
else:
    return call_current_service(request)
```

### Canary Monitoring

```python
# Monitor canary health
import time
from prometheus_client import Counter, Histogram

canary_requests = Counter('canary_requests_total', 'Total canary requests')
canary_errors = Counter('canary_errors_total', 'Total canary errors')
canary_latency = Histogram('canary_latency_seconds', 'Canary request latency')

def check_canary_health():
    """Auto-rollback if canary error rate > threshold."""
    error_rate = canary_errors.get() / max(canary_requests.get(), 1)
    
    if error_rate > 0.05:  # 5% error threshold
        rollback_canary()
        alert("Canary rolled back due to high error rate")
    
    if canary_latency.quantile(0.99) > 2.0:  # P99 > 2s
        rollback_canary()
        alert("Canary rolled back due to high latency")
```

---

## III. Rolling Updates

### Concept

Replace instances one at a time, maintaining capacity throughout.

```
Step 1: [v1] [v1] [v1] [v1] — All running v1
Step 2: [v1] [v1] [v1] [v2] — One instance updated
Step 3: [v1] [v1] [v2] [v2] — Two instances updated
Step 4: [v1] [v2] [v2] [v2] — Three instances updated
Step 5: [v2] [v2] [v2] [v2] — All running v2
```

### Kubernetes Rolling Update

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orderflow
spec:
  replicas: 4
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1        # Max extra pods during update
      maxUnavailable: 0   # Never reduce below desired count
  template:
    spec:
      containers:
      - name: orderflow
        image: orderflow:v1.1
        readinessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 5
          periodSeconds: 5
```

### Health Checks

```python
# FastAPI health check
from fastapi import FastAPI
import asyncio

app = FastAPI()

@app.get("/health")
async def health_check():
    """Verify all dependencies are healthy."""
    checks = {
        "database": await check_database(),
        "redis": await check_redis(),
        "external_api": await check_external_api(),
    }
    
    all_healthy = all(checks.values())
    
    return {
        "status": "healthy" if all_healthy else "unhealthy",
        "checks": checks,
    }

async def check_database() -> bool:
    try:
        await db.execute("SELECT 1")
        return True
    except Exception:
        return False
```

---

## IV. Feature Flags

### Concept

Deploy code to production but control feature visibility without redeployment.

### Implementation

```python
# Simple in-memory feature flags
class FeatureFlags:
    def __init__(self):
        self._flags = {}
    
    def is_enabled(self, flag: str, user_id: int = None) -> bool:
        """Check if a feature flag is enabled."""
        config = self._flags.get(flag, {"enabled": False})
        
        if not config["enabled"]:
            return False
        
        # Percentage rollout
        if "percentage" in config:
            return hash(str(user_id)) % 100 < config["percentage"]
        
        # User whitelist
        if "users" in config:
            return user_id in config["users"]
        
        return True
    
    def set_flag(self, flag: str, **kwargs):
        self._flags[flag] = kwargs

# Usage
features = FeatureFlags()
features.set_flag("new_checkout", enabled=True, percentage=10)

@app.post("/checkout")
async def checkout(request: Request, user: User = Depends(get_user)):
    if features.is_enabled("new_checkout", user.id):
        return await new_checkout_flow(request)
    else:
        return await old_checkout_flow(request)
```

### LaunchDarkly / Unleash Integration

```python
# LaunchDarkly
import ldclient
from ldclient.config import Config

ldclient.set_config(Config("sdk-key-here"))

def is_new_checkout_enabled(user_id: str) -> bool:
    return ldclient.variation("new-checkout", {"key": user_id}, False)

# Unleash
import requests

UNLEASH_URL = "https://your-unleash-instance.com/api"

def is_new_checkout_enabled_unleash(user_id: str) -> bool:
    response = requests.get(
        f"{UNLEASH_URL}/features/new-checkout",
        headers={"Authorization": "token"}
    )
    return response.json()["enabled"]
```

### Feature Flag Lifecycle

```
1. Create flag with default OFF
2. Deploy code behind flag
3. Enable for internal users (dogfooding)
4. Enable for 5% of users (canary)
5. Monitor metrics and errors
6. Increase to 25%, 50%, 100%
7. Remove flag and dead code
```

---

## V. Rollback Strategies

### Automatic Rollback

```python
# Health check based auto-rollback
import time
import subprocess

def deploy_with_rollback(version: str, health_check_url: str):
    """Deploy and auto-rollback if health check fails."""
    
    # Save current version
    current = get_current_version()
    
    # Deploy new version
    subprocess.run(["deploy", version], check=True)
    
    # Wait for startup
    time.sleep(10)
    
    # Health check loop
    for attempt in range(5):
        try:
            response = requests.get(health_check_url, timeout=5)
            if response.status_code == 200:
                print(f"Deploy {version} healthy")
                return True
        except requests.RequestException:
            pass
        
        time.sleep(5)
    
    # Rollback
    print(f"Deploy {version} failed, rolling back to {current}")
    subprocess.run(["deploy", current], check=True)
    return False
```

### Database Rollback

```sql
-- Forward migration
CREATE TABLE orders_v2 (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    total DECIMAL(10,2),
    status VARCHAR(20),
    created_at TIMESTAMP DEFAULT NOW()
);

-- Rollback migration (always write both!)
DROP TABLE IF EXISTS orders_v2;
-- Restore from backup if needed
```

```python
# Migration with rollback
# alembic/versions/001_add_orders.py

def upgrade():
    """Apply migration."""
    op.create_table(
        'orders',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('user_id', sa.Integer, nullable=False),
        sa.Column('total', sa.Numeric(10, 2)),
    )

def downgrade():
    """Rollback migration."""
    op.drop_table('orders')
```

---

## VI. Database Migrations in Deployment

### Migration Strategy

```
1. Write backward-compatible migration
   - New columns should be nullable or have defaults
   - Don't rename columns, add new ones
   - Don't delete columns, deprecate first

2. Deploy migration BEFORE code
   - Migration runs as separate step
   - Code still works with old schema

3. Deploy code that uses new schema
   - Code handles both old and new schema

4. Clean up deprecated columns
   - After all instances updated
```

### Backward-Compatible Migrations

```sql
-- GOOD: Backward compatible
-- Step 1: Add new column (nullable)
ALTER TABLE orders ADD COLUMN status_v2 VARCHAR(20);

-- Step 2: Backfill data
UPDATE orders SET status_v2 = status;

-- Step 3: Add NOT NULL constraint
ALTER TABLE orders ALTER COLUMN status_v2 SET NOT NULL;

-- Step 4: Drop old column (after code migration)
ALTER TABLE orders DROP COLUMN status;

-- BAD: Breaking change
ALTER TABLE orders RENAME COLUMN status TO status_v2;
-- This breaks all running instances immediately
```

---

## VII. CI/CD Pipeline Design

### Pipeline Stages

```yaml
# .github/workflows/deploy.yml
name: Deploy

on:
  push:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install -r requirements.txt
      - run: pytest tests/ -q
      - run: ruff check .
      - run: mypy .

  build:
    needs: test
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: docker build -t orderflow:${{ github.sha }} .
      - run: docker push registry/orderflow:${{ github.sha }}

  deploy-staging:
    needs: build
    runs-on: ubuntu-latest
    environment: staging
    steps:
      - run: kubectl set image deployment/orderflow orderflow=registry/orderflow:${{ github.sha }}
      - run: curl -f https://staging.example.com/health

  deploy-production:
    needs: deploy-staging
    runs-on: ubuntu-latest
    environment: production
    steps:
      - run: kubectl set image deployment/orderflow orderflow=registry/orderflow:${{ github.sha }}
      - run: curl -f https://api.example.com/health
```

### Pipeline Best Practices

| Practice | Why |
|----------|-----|
| Fast feedback | Run lint/tests first, fail fast |
| Immutable artifacts | Build once, deploy same artifact everywhere |
| Environment parity | Staging mirrors production |
| Automated rollbacks | Health checks trigger auto-rollback |
| Manual approval gates | Production deploys need human sign-off |

---

## VIII. Environment Management

### Environment Hierarchy

```
Local Development
    ↓
Integration Testing (CI)
    ↓
Staging (production mirror)
    ↓
Canary (5% production traffic)
    ↓
Production (100% traffic)
```

### Configuration Management

```python
# Environment-based configuration
import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str = "sqlite:///dev.db"
    redis_url: str = "redis://localhost:6379"
    log_level: str = "debug"
    feature_new_checkout: bool = False
    
    class Config:
        env_file = ".env"

# Different settings per environment
settings_map = {
    "development": Settings(log_level="debug", database_url="sqlite:///dev.db"),
    "staging": Settings(log_level="info", database_url="postgresql://staging-db/orders"),
    "production": Settings(log_level="warning", database_url="postgresql://prod-db/orders"),
}

settings = settings_map[os.getenv("ENVIRONMENT", "development")]
```

---

## IX. Container Patterns

### Dockerfile Best Practices

```dockerfile
# Multi-stage build
FROM python:3.11-slim as builder

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

FROM python:3.11-slim

# Non-root user
RUN useradd --create-home appuser
WORKDIR /app

# Copy only what's needed
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY . .

USER appuser
EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Kubernetes Basics

```yaml
# Deployment
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orderflow
spec:
  replicas: 3
  selector:
    matchLabels:
      app: orderflow
  template:
    metadata:
      labels:
        app: orderflow
    spec:
      containers:
      - name: orderflow
        image: orderflow:v1.0
        ports:
        - containerPort: 8000
        resources:
          requests:
            memory: "256Mi"
            cpu: "250m"
          limits:
            memory: "512Mi"
            cpu: "500m"

---
# Service
apiVersion: v1
kind: Service
metadata:
  name: orderflow
spec:
  selector:
    app: orderflow
  ports:
  - port: 80
    targetPort: 8000
  type: LoadBalancer

---
# HPA (Horizontal Pod Autoscaler)
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: orderflow
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: orderflow
  minReplicas: 2
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
```

---

## Decision Tree: Which Deployment Strategy?

```
START
  │
  ├─ Need zero downtime?
  │   ├─ YES → Blue-Green or Rolling Update
  │   └─ NO → Simple deploy (stop-start)
  │
  ├─ Risk tolerance?
  │   ├─ LOW → Blue-Green (instant rollback)
  │   ├─ MEDIUM → Canary (gradual rollout)
  │   └─ HIGH → Rolling Update (default)
  │
  ├─ Feature not ready?
  │   ├─ YES → Feature Flag (deploy off)
  │   └─ NO → Deploy normally
  │
  └─ Database changes needed?
      ├─ Backward-compatible → Migrate first, then deploy
      └─ Breaking change → Blue-Green with dual-write
```

## Anti-Patterns

| Pattern | Problem | Fix |
|---------|---------|-----|
| Big bang deploy | All-or-nothing, high risk | Rolling update or canary |
| No rollback plan | Stuck when things go wrong | Always have rollback ready |
| Manual deploys | Human error, slow | Automate with CI/CD |
| Deploy on Friday | No time to fix issues | Deploy early in week |
| Skip staging | Bugs hit production | Test in production-like env |
| No health checks | Don't know if deploy worked | Always verify health |

## Verification Checklist

- [ ] CI/CD pipeline runs tests before deploy
- [ ] Health checks verify deployment success
- [ ] Rollback strategy defined and tested
- [ ] Database migrations are backward-compatible
- [ ] Feature flags used for risky features
- [ ] Monitoring alerts configured for new deploys
- [ ] Staging environment mirrors production

## Related Skills

- **service-composition** — Service integration patterns for distributed deployments.
- **monitoring-observability** — Logging, metrics, and tracing to verify deployments and detect issues.
- **clean-code** — Clean code is easier to deploy, rollback, and debug in production.
- **pd** — Master orchestrator. Deployment planning is part of Phase 2 (Planning) and Phase 7 (Merge).
