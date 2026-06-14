---
name: performance-patterns
description: "Performance optimization patterns — caching, lazy loading, profiling, memory management, database queries, frontend performance. Use when optimizing speed, reducing resource usage, or fixing performance bottlenecks."
version: 1.0.0
author: ISIS
license: MIT
metadata:
  hermes:
    tags: [performance, optimization, caching, profiling, database, frontend]
    related_skills: [clean-code, database-patterns, monitoring-observability, pd]
---

# Performance Patterns

## Overview

Performance optimization is about making the right trade-offs. Profile first, measure always, optimize the bottleneck. Premature optimization is the root of all evil — but ignoring performance is laziness.

**Core principle:** You can't optimize what you can't measure. Profile before changing code.

## When to Use

- Application feels slow or unresponsive
- Response times exceed SLA requirements
- Memory usage growing unexpectedly
- Database queries taking too long
- Frontend Core Web Vitals failing
- User complaints about speed

**Don't use for:**
- Prototypes or throwaway code
- Features that aren't bottlenecks
- Code that runs once a month

---

## I. Caching Strategies

### Cache Levels

| Level | Location | Latency | Use Case |
|-------|----------|---------|----------|
| **Browser** | Client HTTP cache | ~0ms | Static assets, API responses |
| **CDN** | Edge servers (10-50ms) | ~20ms | Images, videos, static files |
| **Application** | In-process memory | ~0.01ms | Computed results, DB query cache |
| **Database** | Query cache, buffer pool | ~1ms | Repeated queries |
| **Distributed** | Redis/Memcached | ~2ms | Shared state across instances |

### Browser Caching

```python
# FastAPI — Cache-Control headers
from fastapi import Response

@app.get("/api/products")
async def get_products(response: Response):
    response.headers["Cache-Control"] = "public, max-age=300, stale-while-revalidate=60"
    response.headers["ETag"] = compute_etag(products)
    return products
```

```nginx
# Nginx — Static asset caching
location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg)$ {
    expires 1y;
    add_header Cache-Control "public, immutable";
}
```

### CDN Caching

```python
# CloudFront / Cloudflare — Cache invalidation patterns
# Pattern 1: Versioned URLs (best for static assets)
# /assets/app.v2.1.0.js — new version = new URL = cache miss

# Pattern 2: Cache tags (best for dynamic content)
response.headers["Surrogate-Key"] = f"product-{product_id}"
# Purge by tag when product updates
```

### Application-Level Caching

```python
# In-process cache with TTL
from functools import lru_cache
from time import time

_cache = {}
CACHE_TTL = 300  # 5 minutes

def cached(key: str, ttl: int = CACHE_TTL):
    def decorator(func):
        def wrapper(*args, **kwargs):
            now = time()
            if key in _cache:
                value, timestamp = _cache[key]
                if now - timestamp < ttl:
                    return value
            result = func(*args, **kwargs)
            _cache[key] = (result, now)
            return result
        return wrapper
    return decorator

@cached("product_list", ttl=60)
def get_products():
    return db.query("SELECT * FROM products")
```

### Redis Caching

```python
import redis
import json

r = redis.Redis()

def get_product(product_id: int) -> dict:
    cache_key = f"product:{product_id}"
    
    # Check cache first
    cached = r.get(cache_key)
    if cached:
        return json.loads(cached)
    
    # Cache miss — query DB
    product = db.query(Product).get(product_id)
    
    # Store in cache with TTL
    r.setex(cache_key, 300, json.dumps(product.to_dict()))
    return product.to_dict()
```

### Cache Invalidation Patterns

| Pattern | Strategy | When to Use |
|---------|----------|-------------|
| **TTL-based** | Expire after N seconds | Data changes infrequently |
| **Write-through** | Update cache on write | Read-heavy, moderate writes |
| **Write-behind** | Async cache update | High write throughput |
| **Cache-aside** | Lazy load on miss | General purpose |

**The Two Hardest Things:** Cache invalidation and naming things. When in doubt, use TTL.

---

## II. Lazy Loading Patterns

### Image Lazy Loading

```html
<!-- Native lazy loading -->
<img src="product.jpg" loading="lazy" width="300" height="200" alt="Product">

<!-- Intersection Observer for custom lazy loading -->
<script>
const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
        if (entry.isIntersecting) {
            const img = entry.target;
            img.src = img.dataset.src;
            observer.unobserve(img);
        }
    });
});

document.querySelectorAll('img[data-src]').forEach(img => observer.observe(img));
</script>
```

### Component Lazy Loading (React)

```jsx
import { lazy, Suspense } from 'react';

// Lazy load heavy components
const HeavyChart = lazy(() => import('./HeavyChart'));
const AdminPanel = lazy(() => import('./AdminPanel'));

function Dashboard() {
    return (
        <div>
            <h1>Dashboard</h1>
            <Suspense fallback={<Spinner />}>
                <HeavyChart data={chartData} />
            </Suspense>
        </div>
    );
}
```

### Code Splitting

```javascript
// Dynamic imports for route-based splitting
const routes = {
    '/dashboard': () => import('./pages/Dashboard'),
    '/settings': () => import('./pages/Settings'),
    '/reports': () => import('./pages/Reports'),
};

// Load on demand
async function loadRoute(path) {
    const module = await routes[path]();
    return module.default;
}
```

### Database Lazy Loading (ORM)

```python
# SQLAlchemy — Lazy vs Eager loading
class Order(Base):
    __tablename__ = 'orders'
    
    # Lazy loading (default) — loads on first access
    items = relationship("OrderItem", lazy="select")
    
    # Eager loading — loads with parent
    items = relationship("OrderItem", lazy="joined")
    
    # Dynamic loading — returns query, not list
    items = relationship("OrderItem", lazy="dynamic")

# Use joinedload for known relationships
orders = session.query(Order).options(joinedload(Order.items)).all()
```

---

## III. Connection Pooling

### Database Connection Pool

```python
# SQLAlchemy — Connection pool configuration
from sqlalchemy import create_engine

engine = create_engine(
    "postgresql://user:pass@localhost/db",
    pool_size=20,          # Max persistent connections
    max_overflow=10,       # Extra connections when pool is full
    pool_timeout=30,       # Seconds to wait for connection
    pool_recycle=1800,     # Recycle connections after 30 min
    pool_pre_ping=True,    # Verify connections before use
)

# Connection pool monitoring
from sqlalchemy import event

@event.listens_for(engine, "checkout")
def on_checkout(dbapi_conn, connection_rec, connection_proxy):
    """Track connection checkout time."""
    connection_proxy.info['checkout_time'] = time.time()
```

### HTTP Connection Pool (requests)

```python
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Create session with connection pooling
session = requests.Session()

adapter = HTTPAdapter(
    pool_connections=10,   # Number of connection pools
    pool_maxsize=20,       # Max connections per pool
    max_retries=Retry(total=3, backoff_factor=0.5)
)
session.mount("https://", adapter)
session.mount("http://", adapter)

# Reuse session for multiple requests
response = session.get("https://api.example.com/data")
```

---

## IV. Profiling and Benchmarking

### Python Profiling

```python
# cProfile — Function-level profiling
import cProfile
import pstats

def profile_function(func, *args, **kwargs):
    profiler = cProfile.Profile()
    profiler.enable()
    result = func(*args, **kwargs)
    profiler.disable()
    
    stats = pstats.Stats(profiler)
    stats.sort_stats('cumulative')
    stats.print_stats(20)  # Top 20 functions
    
    return result

# Usage
profile_function(process_large_dataset, data)
```

### Line-Level Profiling

```python
# line_profiler — Line-by-line timing
# pip install line_profiler

@profile  # Decorate function to profile
def slow_function(data):
    result = []
    for item in data:           # Line 1
        processed = transform(item)  # Line 2
        result.append(processed)     # Line 3
    return sorted(result)           # Line 4

# Run: kernprof -l -v script.py
```

### Benchmark Pattern

```python
import time
from contextlib import contextmanager

@contextmanager
def benchmark(label: str):
    """Simple benchmark context manager."""
    start = time.perf_counter()
    yield
    elapsed = time.perf_counter() - start
    print(f"{label}: {elapsed:.4f}s")

# Usage
with benchmark("Database query"):
    results = db.query("SELECT * FROM large_table")

# Compare approaches
with benchmark("Approach A (loop)"):
    result_a = [process(x) for x in data]

with benchmark("Approach B (map)"):
    result_b = list(map(process, data))
```

---

## V. Memory Management

### Detecting Memory Leaks

```python
import tracemalloc
import objgraph

# Start tracking allocations
tracemalloc.start()

# ... run code ...

# Take snapshot and compare
snapshot = tracemalloc.take_snapshot()
top_stats = snapshot.statistics('lineno')

print("[ Top 10 memory consumers ]")
for stat in top_stats[:10]:
    print(stat)
```

### Weak References for Caches

```python
import weakref

class ExpensiveObject:
    def __init__(self, data):
        self.data = data

# WeakValueDictionary — auto-cleanup when no strong refs
cache = weakref.WeakValueDictionary()

def get_or_create(key, data):
    if key not in cache:
        cache[key] = ExpensiveObject(data)
    return cache[key]

# Objects are GC'd when no strong references exist
obj = get_or_create("key1", large_dataset)
del obj  # Object may be GC'd, removed from cache
```

### Generators for Memory Efficiency

```python
# BAD: Loads entire file into memory
def read_large_file(path):
    with open(path) as f:
        return f.readlines()  # All lines in memory

# GOOD: Yields one line at a time
def read_large_file(path):
    with open(path) as f:
        for line in f:
            yield line.strip()

# Process millions of lines without OOM
for line in read_large_file("huge_file.log"):
    process(line)
```

---

## VI. CPU Optimization

### Algorithm Complexity

| Complexity | Name | Example | 1K items | 1M items |
|------------|------|---------|----------|----------|
| O(1) | Constant | Hash lookup | 1 | 1 |
| O(log n) | Logarithmic | Binary search | 10 | 20 |
| O(n) | Linear | Array scan | 1,000 | 1,000,000 |
| O(n log n) | Linearithmic | Merge sort | 10,000 | 20,000,000 |
| O(n²) | Quadratic | Nested loops | 1,000,000 | 1,000,000,000,000 |

### Caching Expensive Computations

```python
from functools import lru_cache

@lru_cache(maxsize=128)
def fibonacci(n: int) -> int:
    if n < 2:
        return n
    return fibonacci(n - 1) + fibonacci(n - 2)

# Without cache: O(2^n) — impossibly slow for n > 35
# With cache: O(n) — instant for any n
```

### Batch Processing

```python
# BAD: Process one at a time
for user_id in user_ids:
    send_email(user_id, message)  # 1000 API calls

# GOOD: Batch operations
BATCH_SIZE = 100
for i in range(0, len(user_ids), BATCH_SIZE):
    batch = user_ids[i:i + BATCH_SIZE]
    send_bulk_email(batch, message)  # 10 API calls
```

---

## VII. Network Optimization

### HTTP/2 and Multiplexing

```python
# httpx — HTTP/2 support
import httpx

async with httpx.AsyncClient(http2=True) as client:
    # Multiple requests over single connection
    responses = await asyncio.gather(
        client.get("https://api.example.com/users"),
        client.get("https://api.example.com/products"),
        client.get("https://api.example.com/orders"),
    )
```

### Request Batching (GraphQL)

```graphql
# BAD: Three separate API calls
# GET /api/users/1
# GET /api/users/1/orders
# GET /api/users/1/preferences

# GOOD: Single GraphQL query
query {
  user(id: 1) {
    name
    email
    orders { id, total, date }
    preferences { theme, language }
  }
}
```

### Compression

```python
# Enable gzip compression
from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware

app = FastAPI()
app.add_middleware(GZipMiddleware, minimum_size=500)
```

---

## VIII. Database Query Optimization

### Indexing Strategy

```sql
-- Index selection decision tree
-- 1. WHERE clause columns
CREATE INDEX idx_orders_user_id ON orders(user_id);

-- 2. JOIN columns
CREATE INDEX idx_orders_customer_id ON orders(customer_id);

-- 3. ORDER BY columns
CREATE INDEX idx_orders_created_at ON orders(created_at DESC);

-- 4. Composite index for multi-column queries
CREATE INDEX idx_orders_user_status ON orders(user_id, status);

-- Partial index for filtered queries
CREATE INDEX idx_orders_pending ON orders(created_at)
WHERE status = 'pending';
```

### Query Optimization

```sql
-- BAD: SELECT * loads unnecessary data
SELECT * FROM orders WHERE user_id = 123;

-- GOOD: Select only needed columns
SELECT id, total, status FROM orders WHERE user_id = 123;

-- BAD: N+1 query pattern
SELECT * FROM orders;
-- Then for each order:
SELECT * FROM order_items WHERE order_id = ?;

-- GOOD: JOIN or batch
SELECT o.*, oi.* FROM orders o
JOIN order_items oi ON o.id = oi.order_id
WHERE o.user_id = 123;

-- BAD: Subquery in SELECT
SELECT *, (SELECT COUNT(*) FROM items WHERE order_id = orders.id) as item_count
FROM orders;

-- GOOD: JOIN with aggregation
SELECT o.*, COUNT(i.id) as item_count
FROM orders o
LEFT JOIN items i ON o.id = i.order_id
GROUP BY o.id;
```

### Pagination Patterns

```sql
-- BAD: OFFSET pagination (slow for large offsets)
SELECT * FROM products ORDER BY id LIMIT 20 OFFSET 10000;

-- GOOD: Keyset pagination (consistent performance)
SELECT * FROM products
WHERE id > 10000
ORDER BY id
LIMIT 20;

-- GOOD: Cursor-based pagination
SELECT * FROM products
WHERE created_at < '2024-01-15T10:30:00'
ORDER BY created_at DESC
LIMIT 20;
```

---

## IX. Frontend Performance (Core Web Vitals)

### Core Web Vitals Targets

| Metric | Good | Needs Improvement | Poor |
|--------|------|-------------------|------|
| **LCP** (Largest Contentful Paint) | ≤ 2.5s | ≤ 4.0s | > 4.0s |
| **INP** (Interaction to Next Paint) | ≤ 200ms | ≤ 500ms | > 500ms |
| **CLS** (Cumulative Layout Shift) | ≤ 0.1 | ≤ 0.25 | > 0.25 |

### LCP Optimization

```html
<!-- Preload critical resources -->
<link rel="preload" href="/hero-image.webp" as="image">
<link rel="preload" href="/fonts/main.woff2" as="font" crossorigin>

<!-- Use modern image formats -->
<picture>
    <source srcset="hero.avif" type="image/avif">
    <source srcset="hero.webp" type="image/webp">
    <img src="hero.jpg" alt="Hero" width="1200" height="600">
</picture>
```

### CLS Prevention

```css
/* Reserve space for ads/images */
img, video {
    aspect-ratio: 16/9;
    width: 100%;
    height: auto;
}

/* Reserve space for dynamic content */
.ad-slot {
    min-height: 250px;
}
```

### INP Optimization

```javascript
// Break long tasks into smaller chunks
function processLargeDataset(data) {
    const CHUNK_SIZE = 100;
    let index = 0;
    
    function processChunk(deadline) {
        while (index < data.length && deadline.timeRemaining() > 0) {
            processItem(data[index]);
            index++;
        }
        
        if (index < data.length) {
            requestIdleCallback(processChunk);
        }
    }
    
    requestIdleCallback(processChunk);
}

// Use web workers for heavy computation
const worker = new Worker('processor.js');
worker.postMessage({ data: largeDataset });
worker.onmessage = (e) => updateUI(e.data);
```

---

## Decision Tree: What to Optimize?

```
START
  │
  ├─ App feels slow?
  │   ├─ Initial load slow → Optimize LCP (preload, lazy load, CDN)
  │   ├─ Interactions laggy → Optimize INP (break long tasks, web workers)
  │   └─ Layout jumps → Fix CLS (reserve space, font-display)
  │
  ├─ API responses slow?
  │   ├─ Database queries → Add indexes, optimize queries
  │   ├─ Computation → Cache results, batch operations
  │   └─ Network → Connection pooling, HTTP/2, compression
  │
  ├─ Memory issues?
  │   ├─ Growing over time → Check for leaks (tracemalloc)
  │   ├─ Large datasets → Use generators, streaming
  │   └─ Caches too large → Add TTL, weak references
  │
  └─ Database bottleneck?
      ├─ Slow queries → EXPLAIN ANALYZE, add indexes
      ├─ Too many queries → Batch, JOIN, eager loading
      └─ Connection limits → Connection pooling
```

## Anti-Patterns

| Pattern | Problem | Fix |
|---------|---------|-----|
| Premature optimization | Wasted time on non-bottlenecks | Profile first, measure always |
| Caching everything | Cache invalidation complexity | Cache only hot paths |
| N+1 queries | 100x more DB calls than needed | Use JOINs or eager loading |
| SELECT * | Loads unused data | Select only needed columns |
| No connection pooling | Connection overhead per request | Use connection pools |
| Ignoring frontend | Slow LCP/INP/CLS | Measure Core Web Vitals |

## Verification Checklist

- [ ] Profiled before optimizing (not guessing)
- [ ] Measured baseline before changes
- [ ] Caching strategy defined (TTL, invalidation)
- [ ] Database queries optimized (indexes, no N+1)
- [ ] Connection pooling configured
- [ ] Frontend Core Web Vitals measured
- [ ] Memory usage monitored for leaks
- [ ] Load testing performed for critical paths

## Related Skills

- **clean-code** — Clean code is easier to profile and optimize. Small functions isolate bottlenecks.
- **database-patterns** — Schema design, indexing, and migration patterns directly impact query performance.
- **monitoring-observability** — Logging, metrics, and tracing identify performance bottlenecks in production.
- **pd** — Master orchestrator. Performance optimization fits into Phase 4 (Coding) and Phase 5 (Testing).
