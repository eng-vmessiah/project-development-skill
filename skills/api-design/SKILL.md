---
name: api-design
description: "REST API design patterns — resource naming, HTTP semantics, status codes, versioning, pagination, error handling, rate limiting, and OpenAPI specs. Use when designing or reviewing REST APIs."
version: 1.0.0
license: MIT
metadata:
  hermes:
    tags: [api, rest, http, openapi, pagination, versioning, design]
    related_skills: [clean-code, design-patterns, auth-patterns, pd]
---

# REST API Design Patterns

## Overview

Well-designed APIs are predictable, consistent, and self-documenting. They follow established conventions so that consumers can learn the patterns once and apply them everywhere. This skill covers every aspect of REST API design — from resource naming to error handling to rate limiting.

**Core principle:** Design APIs for the consumer, not the implementation. The internal data model should never leak into the API surface.

## When to Use

- Designing a new API (REST, REST-like)
- Reviewing an existing API for consistency
- Adding new endpoints to an existing API
- Writing OpenAPI/Swagger specifications
- Evaluating API versioning strategies

**Don't use for:**
- GraphQL APIs (different paradigm entirely)
- gRPC APIs (use protobuf conventions)
- Webhook-only designs (simpler patterns apply)

---

## I. Resource Naming Conventions

### Rules

| # | Rule | Bad | Good |
|---|------|-----|------|
| 1 | **Use plural nouns** | `/user`, `/getUser` | `/users` |
| 2 | **Use nouns, not verbs** | `/getUsers`, `/createOrder` | `/users`, `/orders` |
| 3 | **Use lowercase with hyphens** | `/userProfiles`, `/user_profiles` | `/user-profiles` |
| 4 | **Nest for relationships** | `/orders?userId=123` | `/users/123/orders` |
| 5 | **Limit nesting depth** | `/users/1/orders/5/items/3/reviews` | `/orders/5/items/3/reviews` |
| 6 | **Use query params for filtering** | `/users/active` | `/users?status=active` |
| 7 | **Identify resources by ID in path** | `/users?id=123` | `/users/123` |

### Resource Naming Decision Tree

```
What is the resource?
  → A collection of things? → Plural noun: /users, /orders
  → A specific instance? → /resources/{id}: /users/42
  → A sub-resource? → /resources/{id}/sub-resources: /users/42/orders
  → An action? → /resources/{id}/action: /orders/42/cancel

Is the action a standard CRUD operation?
  → YES → Use the standard HTTP methods on the resource
  → NO → POST to /resources/{id}/action (e.g., POST /orders/42/cancel)

How deep should nesting go?
  → Maximum 3 levels of nesting
  → Beyond that, use query params or separate endpoints
```

### Complete Resource Map (E-commerce Example)

```
GET    /products              — List products
POST   /products              — Create product
GET    /products/42           — Get product
PUT    /products/42           — Replace product
PATCH  /products/42           — Update product
DELETE /products/42           — Delete product

GET    /products/42/variants  — List variants for product
POST   /products/42/variants  — Add variant to product

GET    /users/7/orders        — List orders for user
GET    /users/7/orders/12     — Get specific order for user

POST   /orders/12/cancel      — Cancel order (action endpoint)
POST   /orders/12/approve     — Approve order (action endpoint)
```

---

## II. HTTP Methods Semantics

### Method Reference

| Method | Purpose | Idempotent | Safe | Request Body | Typical Response |
|--------|---------|------------|------|-------------|-----------------|
| **GET** | Retrieve resource(s) | Yes | Yes | No | 200 OK |
| **POST** | Create resource or trigger action | No | No | Yes | 201 Created |
| **PUT** | Replace entire resource | Yes | No | Yes | 200 OK or 204 No Content |
| **PATCH** | Partial update | No* | No | Yes | 200 OK or 204 No Content |
| **DELETE** | Remove resource | Yes | No | No | 204 No Content or 200 OK |

*PATCH can be idempotent if operations are designed to be (e.g., set X to Y, not increment X by Y).

### Decision Tree: PUT vs PATCH

```
Do you have the complete replacement resource?
  → YES → Use PUT (full replacement)
  → NO ↓

Are you updating specific fields only?
  → YES → Use PATCH (partial update)
  → NO ↓

Is the update atomic (all fields or nothing)?
  → YES → Use PUT with complete resource
  → NO → Use PATCH with explicit operations
```

### POST for Non-CRUD Actions

```python
# Instead of: PUT /orders/42/status { "status": "cancelled" }
# Use:
POST /orders/42/cancel
# Body: {} (or reason details)
# Response: 200 OK with updated order, or 409 Conflict if already cancelled

POST /orders/42/approve
# Body: { "notes": "Approved by manager" }
# Response: 200 OK with updated order
```

---

## III. Status Codes

### Decision Tree

```
Did the request succeed?
  → YES ↓
    Was a resource created?
      → YES → 201 Created (include Location header)
    Is there content to return?
      → YES → 200 OK (with body)
      → NO → 204 No Content
    Did it trigger a background process?
      → YES → 202 Accepted (include polling URL)
  → NO ↓
    Is the request malformed?
      → YES → 400 Bad Request (syntax/semantics error)
      → NO ↓
    Is authentication required?
      → YES → 401 Unauthorized
    Is authorization failing?
      → YES → 403 Forbidden
    Does the resource exist?
      → NO → 404 Not Found
    Is there a conflict with current state?
      → YES → 409 Conflict
    Is validation failing?
      → YES → 422 Unprocessable Entity
    Is the client rate limited?
      → YES → 429 Too Many Requests
    Is something wrong with the server?
      → YES → 500 Internal Server Error
```

### Status Code Reference

| Code | Meaning | When to Use |
|------|---------|-------------|
| **200** | OK | Successful GET, PUT, PATCH, DELETE with response body |
| **201** | Created | Successful POST that created a resource. Include `Location` header. |
| **202** | Accepted | Request accepted for processing (async). Include polling URL. |
| **204** | No Content | Successful PUT/PATCH/DELETE with no body to return. |
| **400** | Bad Request | Malformed request (invalid JSON, missing required fields). |
| **401** | Unauthorized | Missing or invalid authentication. Include `WWW-Authenticate`. |
| **403** | Forbidden | Authenticated but not authorized for this action. |
| **404** | Not Found | Resource doesn't exist (or you don't want to reveal it exists). |
| **409** | Conflict | State conflict (e.g., duplicate creation, version mismatch). |
| **422** | Unprocessable Entity | Request is well-formed but semantically invalid (validation errors). |
| **429** | Too Many Requests | Rate limit exceeded. Include `Retry-After` header. |
| **500** | Internal Server Error | Unexpected server error. Never expose internals. |

### 404 vs 410 Gone

```
Does the resource ever exist?
  → NO → 404 Not Found
  → YES ↓
    Is the deletion permanent and documented?
      → YES → 410 Gone (resource permanently removed)
      → NO → 404 Not Found (safe default)
```

---

## IV. Versioning Strategies

### Strategy Comparison

| Strategy | Example | Pros | Cons |
|----------|---------|------|------|
| **URL path** | `/v1/users` | Explicit, cacheable, easy to route | pollutes URL space |
| **Query param** | `/users?version=1` | Simple | easy to forget, caching issues |
| **Header** | `Accept: application/vnd.api.v1+json` | Clean URLs | hidden, harder to test |
| **Content negotiation** | `Accept: application/vnd.api+json;version=1` | Most RESTful | complex, tooling support |

### Decision Tree

```
Do you need versioning?
  → NO → Don't version. Use additive changes only.
  → YES ↓

Are you building a public API?
  → YES → Use URL path versioning (/v1/). Most explicit, easiest for consumers.
  → NO ↓

Is this an internal API with controlled consumers?
  → YES → Use header versioning. Cleaner URLs, controlled rollout.
  → NO → URL path versioning. Safest default.

When to create a new version?
  → Breaking change (removing/renaming fields, changing types) → New version
  → Additive change (new fields, new endpoints) → Same version
  → Deprecation → Mark old version as deprecated, set Sunset header
```

### Versioning Implementation

```python
# URL path versioning (FastAPI)
from fastapi import FastAPI, APIRouter

app = FastAPI()
v1 = APIRouter(prefix="/v1")
v2 = APIRouter(prefix="/v2")

@v1.get("/users/{user_id}")
async def get_user_v1(user_id: int):
    return {"id": user_id, "name": "John"}

@v2.get("/users/{user_id}")
async def get_user_v2(user_id: int):
    return {"id": user_id, "name": "John", "email": "john@example.com"}

app.include_router(v1)
app.include_router(v2)
```

---

## V. Pagination

### Strategy Comparison

| Strategy | How It Works | Best For | Cons |
|----------|-------------|----------|------|
| **Offset** | `?page=3&per_page=20` | Small datasets, simple UIs | Skips items on insert/delete |
| **Cursor** | `?cursor=abc123` | Large datasets, real-time feeds | Can't jump to arbitrary page |
| **Keyset** | `?created_after=2024-01-15&id_after=42` | High performance, stable | Requires sortable, unique fields |

### Offset Pagination

```json
// Request
GET /users?page=3&per_page=20

// Response
{
  "data": [...],
  "pagination": {
    "page": 3,
    "per_page": 20,
    "total": 342,
    "total_pages": 18,
    "has_next": true,
    "has_prev": true
  }
}
```

### Cursor Pagination

```json
// Request
GET /feed?limit=20&cursor=eyJpZCI6MTIzLCJjcmVhdGVkX2F0IjoiMjAyNC0wMS0xNSJ9

// Response
{
  "data": [...],
  "pagination": {
    "next_cursor": "eyJpZCI6MTQzLCJjcmVhdGVkX2F0IjoiMjAyNC0wMS0xNiJ9",
    "has_next": true
  }
}
```

### Keyset Pagination

```json
// Request
GET /products?created_after=2024-01-15T10:30:00Z&id_after=42&limit=20

// Response
{
  "data": [...],
  "pagination": {
    "next_cursor": {
      "created_after": "2024-01-16T08:15:00Z",
      "id_after": 85
    },
    "has_next": true
  }
}
```

### Decision Tree

```
Do you need to show "Page X of Y" in UI?
  → YES → Offset pagination
  → NO ↓

Is the dataset changing frequently (real-time)?
  → YES → Cursor or keyset pagination
  → NO ↓

Do consumers need random page access?
  → YES → Offset pagination
  → NO → Cursor pagination (simpler implementation)
```

---

## VI. Filtering, Sorting, and Field Selection

### Filtering

```json
// Query params for filtering
GET /products?category=electronics&price_min=50&price_max=200&in_stock=true

// Array filtering (comma-separated)
GET /users?status=active,pending

// Date range filtering
GET /orders?created_after=2024-01-01&created_before=2024-12-31
```

### Sorting

```json
// Single field
GET /products?sort=price

// Direction
GET /products?sort=-price        // descending
GET /products?sort=+price        // ascending (explicit)
GET /products?sort=price:desc    // explicit direction

// Multi-field
GET /products?sort=-rating,price  // by rating desc, then price asc
```

### Field Selection (Sparse Fieldsets)

```json
// Request specific fields
GET /users/42?fields=id,name,email

// Response
{
  "id": 42,
  "name": "John Doe",
  "email": "john@example.com"
}
```

### Filter Implementation (Python)

```python
from fastapi import Query

@app.get("/products")
async def list_products(
    category: str | None = Query(None),
    price_min: float | None = Query(None, ge=0),
    price_max: float | None = Query(None, ge=0),
    in_stock: bool | None = Query(None),
    sort: str = Query("-created_at"),
    fields: list[str] | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
):
    query = ProductQuery()

    if category:
        query = query.filter(category=category)
    if price_min is not None:
        query = query.filter(price__gte=price_min)
    if price_max is not None:
        query = query.filter(price__lte=price_max)
    if in_stock is not None:
        query = query.filter(stock__gt=0) if in_stock else query.filter(stock=0)

    query = query.order_by(sort)
    query = query.select_fields(fields) if fields else query
    query = query.paginate(page, per_page)

    return await query.execute()
```

---

## VII. Error Response Format (RFC 7807 Problem Details)

### Standard Error Format

```json
{
  "type": "https://api.example.com/errors/validation-error",
  "title": "Validation Error",
  "status": 422,
  "detail": "The request body contains invalid fields",
  "instance": "/products",
  "errors": [
    {
      "field": "price",
      "code": "invalid_value",
      "message": "Price must be greater than 0"
    },
    {
      "field": "name",
      "code": "missing_required",
      "message": "Name is required"
    }
  ]
}
```

### Error Response Headers

```http
HTTP/1.1 422 Unprocessable Entity
Content-Type: application/problem+json
X-Request-ID: req_abc123
```

### Implementation

```python
from fastapi import Request
from fastapi.responses import JSONResponse

class ProblemDetail(Exception):
    def __init__(
        self,
        status: int,
        title: str,
        detail: str,
        type: str = "about:blank",
        errors: list[dict] | None = None,
    ):
        self.status = status
        self.title = title
        self.detail = detail
        self.type = type
        self.errors = errors or []

@app.exception_handler(ProblemDetail)
async def problem_detail_handler(request: Request, exc: ProblemDetail):
    return JSONResponse(
        status_code=exc.status,
        content={
            "type": exc.type,
            "title": exc.title,
            "status": exc.status,
            "detail": exc.detail,
            "instance": str(request.url),
            "errors": exc.errors,
        },
        headers={"Content-Type": "application/problem+json"},
    )
```

---

## VIII. Rate Limiting

### Rate Limit Response

```http
HTTP/1.1 429 Too Many Requests
Content-Type: application/json
Retry-After: 30
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 0
X-RateLimit-Reset: 1704067200
```

### Rate Limit Headers

| Header | Description |
|--------|-------------|
| `X-RateLimit-Limit` | Max requests per window |
| `X-RateLimit-Remaining` | Requests remaining in window |
| `X-RateLimit-Reset` | Unix timestamp when window resets |
| `Retry-After` | Seconds to wait (on 429) |

### Token Bucket Implementation

```python
import time
from collections import defaultdict

class TokenBucket:
    def __init__(self, capacity: int, refill_rate: float):
        self.capacity = capacity
        self.refill_rate = refill_rate  # tokens per second
        self.tokens = defaultdict(lambda: capacity)
        self.last_refill = defaultdict(time.time)

    def allow(self, key: str) -> tuple[bool, dict]:
        now = time.time()
        elapsed = now - self.last_refill[key]

        # Refill tokens
        self.tokens[key] = min(
            self.capacity,
            self.tokens[key] + elapsed * self.refill_rate
        )
        self.last_refill[key] = now

        headers = {
            "X-RateLimit-Limit": str(self.capacity),
            "X-RateLimit-Remaining": str(max(0, int(self.tokens[key]) - 1)),
            "X-RateLimit-Reset": str(int(now + (self.capacity - self.tokens[key]) / self.refill_rate)),
        }

        if self.tokens[key] >= 1:
            self.tokens[key] -= 1
            return True, headers
        else:
            retry_after = int((1 - self.tokens[key]) / self.refill_rate) + 1
            headers["Retry-After"] = str(retry_after)
            return False, headers
```

### Rate Limiting Decision Tree

```
What are you rate limiting?
  → Global (all endpoints) → Same limits for everyone
  → Per-endpoint → Stricter for expensive endpoints
  → Per-user → Different tiers (free vs paid)
  → Per-IP → Protects against anonymous abuse

What algorithm?
  → Fixed window → Simple, but bursty at window boundaries
  → Sliding window → Smoother, more complex
  → Token bucket → Flexible, allows controlled bursts
  → Leaky bucket → Smooths out bursts, constant output rate

Where to implement?
  → API gateway → Centralized, infrastructure-level
  → Application middleware → Per-service control
  → Both → Gateway for coarse limits, app for fine-grained
```

---

## IX. OpenAPI Specification Patterns

### Spec Structure

```yaml
openapi: "3.0.3"
info:
  title: Product API
  version: "1.0.0"
  description: API for managing products
  contact:
    name: API Support
    email: support@example.com

servers:
  - url: https://api.example.com/v1
    description: Production
  - url: https://staging-api.example.com/v1
    description: Staging

paths:
  /products:
    get:
      operationId: listProducts
      summary: List all products
      tags: [products]
      parameters:
        - $ref: '#/components/parameters/PageParam'
        - $ref: '#/components/parameters/PerPageParam'
      responses:
        '200':
          description: Paginated list of products
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ProductList'
        '401':
          $ref: '#/components/responses/Unauthorized'
        '429':
          $ref: '#/components/responses/RateLimited'

    post:
      operationId: createProduct
      summary: Create a new product
      tags: [products]
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/ProductCreate'
      responses:
        '201':
          description: Product created
          headers:
            Location:
              schema:
                type: string
              description: URL of created product
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Product'

components:
  schemas:
    Product:
      type: object
      required: [id, name, price, created_at]
      properties:
        id:
          type: integer
          format: int64
        name:
          type: string
          minLength: 1
          maxLength: 255
        price:
          type: number
          format: decimal
          minimum: 0
        created_at:
          type: string
          format: date-time

    ProductCreate:
      type: object
      required: [name, price]
      properties:
        name:
          type: string
          minLength: 1
          maxLength: 255
        price:
          type: number
          format: decimal
          minimum: 0

  parameters:
    PageParam:
      name: page
      in: query
      schema:
        type: integer
        minimum: 1
        default: 1
    PerPageParam:
      name: per_page
      in: query
      schema:
        type: integer
        minimum: 1
        maximum: 100
        default: 20

  responses:
    Unauthorized:
      description: Authentication required
      content:
        application/problem+json:
          schema:
            $ref: '#/components/schemas/ProblemDetail'
    RateLimited:
      description: Rate limit exceeded
      headers:
        Retry-After:
          schema:
            type: integer
      content:
        application/problem+json:
          schema:
            $ref: '#/components/schemas/ProblemDetail'
```

---

## X. Idempotency

### Idempotency Decision Tree

```
Is the operation idempotent by nature?
  → GET, PUT, DELETE → YES (inherently idempotent)
  → POST → NO (inherently non-idempotent)
  → PATCH → Depends on implementation

Should this POST be idempotent?
  → Creating a resource with a client-generated ID → YES, use PUT
  → Submitting a payment → YES, use idempotency key
  → Sending a notification → Maybe, depends on semantics
  → Triggering a one-time action → NO

How to implement idempotency for POST?
  → Client sends Idempotency-Key header
  → Server stores key + response for TTL (24h typical)
  → If same key received, return cached response
  → If key expired, process as new request
```

### Idempotency Key Implementation

```python
import uuid
from fastapi import Header

@app.post("/payments")
async def create_payment(
    payment: PaymentCreate,
    idempotency_key: str = Header(None, alias="Idempotency-Key"),
):
    if not idempotency_key:
        idempotency_key = str(uuid.uuid4())

    # Check if we've seen this key
    cached = await redis.get(f"idempotency:{idempotency_key}")
    if cached:
        return JSONResponse(
            status_code=200,
            content=json.loads(cached),
            headers={"Idempotent-Replay": "true"},
        )

    # Process payment
    result = await process_payment(payment)

    # Cache response for 24 hours
    await redis.setex(
        f"idempotency:{idempotency_key}",
        86400,
        json.dumps(result),
    )

    return result
```

---

## XI. HATEOAS Basics

### What is HATEOAS?

Hypermedia as the Engine of Application State. Responses include links that tell the client what actions are available next.

```json
{
  "id": 42,
  "name": "Order #42",
  "status": "pending",
  "total": 99.99,
  "_links": {
    "self": { "href": "/orders/42", "method": "GET" },
    "approve": { "href": "/orders/42/approve", "method": "POST" },
    "cancel": { "href": "/orders/42/cancel", "method": "POST" },
    "customer": { "href": "/users/7", "method": "GET" },
    "items": { "href": "/orders/42/items", "method": "GET" }
  }
}
```

### When to Use HATEOAS

```
Building a public API consumed by unknown clients?
  → YES → Consider HATEOAS (discoverability)
  → NO ↓

Building an API for a known frontend team?
  → Maybe → HATEOAS adds complexity without much benefit
  → Consider → Just document the contract well

Building a hypermedia-driven API (HTML-like)?
  → YES → HATEOAS is essential
```

### Implementation Pattern

```python
from pydantic import BaseModel

class Link(BaseModel):
    href: str
    method: str = "GET"

class OrderResponse(BaseModel):
    id: int
    name: str
    status: str
    total: float
    _links: dict[str, Link]

def order_links(order: Order) -> dict[str, Link]:
    links = {
        "self": Link(href=f"/orders/{order.id}", method="GET"),
        "items": Link(href=f"/orders/{order.id}/items", method="GET"),
    }

    if order.status == "pending":
        links["approve"] = Link(href=f"/orders/{order.id}/approve", method="POST")
        links["cancel"] = Link(href=f"/orders/{order.id}/cancel", method="POST")

    links["customer"] = Link(href=f"/users/{order.user_id}", method="GET")

    return links
```

---

## XII. Content Negotiation

### Accept Header

```http
# Client requests JSON
GET /users/42
Accept: application/json

# Client requests XML
GET /users/42
Accept: application/xml

# Client accepts multiple formats
GET /users/42
Accept: application/json, application/xml;q=0.9, */*;q=0.8
```

### Content Negotiation Rules

```
Does the client send an Accept header?
  → NO → Default to application/json
  → YES ↓

Do we support the requested format?
  → YES → Respond in that format
  → NO ↓

Is there a compatible format (q-factor matching)?
  → YES → Use the best compatible format
  → NO → 406 Not Acceptable

What if client sends Accept: */*?
  → Default to application/json
```

### Implementation

```python
from fastapi import Request
from fastapi.responses import JSONResponse, XMLResponse

@app.get("/users/{user_id}")
async def get_user(user_id: int, request: Request):
    user = await get_user_or_404(user_id)
    accept = request.headers.get("accept", "application/json")

    if "application/xml" in accept:
        return XMLResponse(content=to_xml(user))
    elif "text/csv" in accept:
        return PlainTextResponse(content=to_csv(user), media_type="text/csv")
    else:
        return JSONResponse(content=user.model_dump())
```

---

## XIII. Complete API Design Checklist

### Before Starting

- [ ] Resources identified and named (plural nouns)
- [ ] HTTP methods assigned correctly
- [ ] Status codes defined for each response
- [ ] Error format consistent (RFC 7807)
- [ ] Pagination strategy chosen
- [ ] Filtering/sorting approach defined
- [ ] Versioning strategy decided

### Before Shipping

- [ ] OpenAPI spec complete and valid
- [ ] All endpoints have examples
- [ ] Error responses documented
- [ ] Rate limits defined and documented
- [ ] Idempotency implemented for critical operations
- [ ] Content negotiation working
- [ ] Security headers in place

### Performance

- [ ] Pagination limits enforced (max per_page)
- [ ] Database queries optimized for list endpoints
- [ ] Caching headers set (ETag, Cache-Control)
- [ ] Compression enabled (gzip/brotli)

---

## References

- **RFC 7231** — HTTP/1.1 Semantics and Content
- **RFC 7807** — Problem Details for HTTP APIs
- **RFC 6585** — Additional HTTP Status Codes (429)
- **Microsoft REST API Guidelines** — https://github.com/microsoft/api-guidelines
- **Zalando RESTful API Guidelines** — https://opensource.zalando.com/restful-api-guidelines/
- **OpenAPI Specification** — https://spec.openapis.org/oas/v3.0.3

## Related Skills

- **clean-code** — Clear naming and small functions make API handlers maintainable.
- **design-patterns** — Façade, Adapter, and Proxy patterns shape clean API boundaries.
- **auth-patterns** — JWT, OAuth, and API key patterns for securing endpoints.
- **pd** — Master orchestrator. API design is part of Phase 1 (Brainstorming) and Phase 2 (Planning).
