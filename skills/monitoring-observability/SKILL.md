---
name: monitoring-observability
description: "Monitoring and observability — structured logging, metrics, distributed tracing, health checks, alerting, dashboards, and SLI/SLO/SLA concepts. Use when setting up observability for applications or services."
version: 1.0.0
license: MIT
metadata:
  hermes:
    tags: [monitoring, observability, logging, metrics, tracing, alerting, sre]
    related_skills: [service-composition, clean-code, pd, design-patterns]
---

# Monitoring & Observability

## Overview

Monitoring tells you what's happening. Observability tells you *why*. This skill covers the three pillars of observability — logs, metrics, and traces — along with practical patterns for health checks, alerting, and dashboard design.

**Core principle:** You can't fix what you can't see. Instrument first, optimize second.

## When to Use

- Setting up a new application or service
- Debugging production issues
- Designing health check endpoints
- Creating dashboards or alerts
- Planning SLOs and SLAs
- On-call runbook development

**Don't skip for:**
- "We'll add monitoring later" — you need it from day one
- "It's a small app" — small apps fail too
- "We have logs" — logs without structure are noise

---

## I. Three Pillars of Observability

### Overview

| Pillar | What It Tells You | Example Tools |
|--------|-------------------|---------------|
| **Logs** | What happened (discrete events) | ELK, Loki, CloudWatch |
| **Metrics** | How much/how fast (numerical time series) | Prometheus, Datadog, Grafana |
| **Traces** | How a request flows (distributed path) | Jaeger, Zipkin, OpenTelemetry |

### When to Use Each

```
What are you trying to understand?
  → What happened at a specific time? → Logs
  → Is the system healthy right now? → Metrics
  → Why is this request slow? → Traces
  → What's the error rate? → Metrics
  → What's the full context of an error? → Logs + Traces
  → What's the trend over time? → Metrics
```

### Correlation

The key to observability is correlating across pillars:

```
Metric: Error rate spike detected at 14:32
  → Log: Search for errors at 14:32 → "Connection refused to database"
  → Trace: Find slow request → Database call taking 5000ms
  → Root cause: Database failover in progress
```

Implementation:

```python
import structlog
from opentelemetry import trace

# Correlation ID ties everything together
def setup_logging(service_name: str):
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.BoundLogger,
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
    )

# Middleware to inject correlation ID
@app.middleware("http")
async def correlation_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))

    # Bind to structlog context (all logs in this request will include it)
    structlog.contextvars.bind_contextvars(request_id=request_id)

    # Bind to OpenTelemetry trace
    span = trace.get_current_span()
    span.set_attribute("http.request_id", request_id)

    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id

    return response
```

---

## II. Structured Logging

### Log Format

```json
{
  "timestamp": "2024-01-15T10:30:00.123Z",
  "level": "error",
  "service": "order-api",
  "request_id": "req_abc123",
  "user_id": 42,
  "message": "Failed to process payment",
  "error": {
    "type": "PaymentGatewayError",
    "message": "Connection timeout",
    "stack": "..."
  },
  "context": {
    "order_id": 789,
    "amount": 99.99,
    "currency": "USD",
    "payment_method": "stripe"
  }
}
```

### Log Levels Decision Tree

```
What is the severity?
  → FATAL → Application is about to crash (unrecoverable)
  → ERROR → Something failed that shouldn't have (needs attention)
  → WARN → Something unexpected but recoverable (investigate later)
  → INFO → Normal operation (important business events)
  → DEBUG → Detailed diagnostic info (development only)

When to use each level:

FATAL: Database connection pool exhausted, OOM, corrupted state
ERROR: Unhandled exception, failed payment, external service down
WARN: Rate limit approaching, deprecated API call, retry attempt
INFO: Request processed, user logged in, order created, payment received
DEBUG: SQL query executed, cache hit/miss, function entry/exit
```

### Logging Anti-Patterns

| Anti-Pattern | Problem | Fix |
|-------------|---------|-----|
| Logging sensitive data | Security breach, compliance violation | Mask/redact PII, passwords, tokens |
| Logging in loops | Log spam, performance degradation | Log summary, not individual items |
| Unstructured logs | Can't query or aggregate | Use JSON structured logging |
| Logging at wrong level | Noise in production | DEBUG in dev, INFO in prod |
| No context in logs | Can't correlate events | Always include request_id, user_id |

### PII Redaction

```python
import re
from structlog import processors

SENSITIVE_PATTERNS = {
    "email": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
    "phone": r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b",
    "ssn": r"\b\d{3}-\d{2}-\d{4}\b",
    "credit_card": r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b",
}

def redact_pii(logger, method_name, event_dict):
    for key, value in event_dict.items():
        if isinstance(value, str):
            for pii_type, pattern in SENSITIVE_PATTERNS.items():
                event_dict[key] = re.sub(pattern, f"[REDACTED_{pii_type.upper()}]", value)
    return event_dict
```

---

## III. Metrics

### Metric Types

| Type | What It Measures | Example | When to Use |
|------|-----------------|---------|-------------|
| **Counter** | Cumulative count | `requests_total` | Things that only go up |
| **Gauge** | Current value | `cpu_usage_percent` | Things that go up and down |
| **Histogram** | Value distribution | `request_duration_seconds` | Latency, size distributions |
| **Summary** | Quantiles | `request_duration_seconds` | Like histogram, pre-calculated |

### RED Method (Request-Driven Services)

```
Rate:     requests per second (throughput)
Errors:   errors per second (failure rate)
Duration: request latency (latency distribution)

Prometheus queries:
  rate(http_requests_total[5m])                    — Rate
  rate(http_requests_total{status=~"5.."}[5m])     — Errors
  histogram_quantile(0.99, rate(http_request_duration_seconds_bucket[5m]))  — P99 latency
```

### USE Method (Resources)

```
Utilization: % of resource in use
Saturation:  Work queued but not yet processed
Errors:      Error events on the resource

Prometheus queries:
  node_cpu_seconds_total / time()                  — CPU utilization
  node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes  — Memory
  node_filesystem_avail_bytes / node_filesystem_size_bytes     — Disk
```

### Prometheus Implementation

```python
from prometheus_client import Counter, Histogram, Gauge, generate_latest
import time

# Define metrics
REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"],
)

REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "endpoint"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

ACTIVE_CONNECTIONS = Gauge(
    "active_connections",
    "Number of active connections",
)

# Middleware to collect metrics
@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    ACTIVE_CONNECTIONS.inc()
    start_time = time.time()

    response = await call_next(request)

    duration = time.time() - start_time
    REQUEST_COUNT.labels(
        method=request.method,
        endpoint=request.url.path,
        status=response.status_code,
    ).inc()
    REQUEST_LATENCY.labels(
        method=request.method,
        endpoint=request.url.path,
    ).observe(duration)
    ACTIVE_CONNECTIONS.dec()

    return response

# Metrics endpoint
@app.get("/metrics")
async def metrics():
    return Response(
        content=generate_latest(),
        media_type="text/plain",
    )
```

---

## IV. Health Check Patterns

### Liveness vs Readiness

| Check | Purpose | What It Tests | Failure Action |
|-------|---------|---------------|----------------|
| **Liveness** | Is the app alive? | Core process running, not deadlocked | Restart the pod/container |
| **Readiness** | Is the app ready to serve? | Dependencies available, can handle traffic | Remove from load balancer |
| **Startup** | Is the app started? | Initialization complete | Wait before checking liveness |

### Health Check Decision Tree

```
What are you checking?
  → Is the process running? → Liveness check
  → Can it serve traffic? → Readiness check
  → Has initialization completed? → Startup check

What dependencies to check in readiness?
  → Database → Can execute simple query?
  → Cache → Can ping Redis?
  → Message queue → Can connect?
  → External API → Can reach endpoint?

Should you check external dependencies?
  → Readiness: YES (don't send traffic if deps are down)
  → Liveness: NO (app is alive even if DB is temporarily down)
```

### Implementation

```python
from fastapi import FastAPI, Response
from enum import Enum

class HealthStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"

app = FastAPI()

@app.get("/health/live")
async def liveness():
    """Liveness: Is the process running?"""
    return {"status": HealthStatus.HEALTHY}

@app.get("/health/ready")
async def readiness():
    """Readiness: Can we serve traffic?"""
    checks = {}

    # Database check
    try:
        await db.execute("SELECT 1")
        checks["database"] = HealthStatus.HEALTHY
    except Exception as e:
        checks["database"] = HealthStatus.UNHEALTHY

    # Redis check
    try:
        await redis.ping()
        checks["redis"] = HealthStatus.HEALTHY
    except Exception as e:
        checks["redis"] = HealthStatus.UNHEALTHY

    # Overall status
    if all(v == HealthStatus.HEALTHY for v in checks.values()):
        status = HealthStatus.HEALTHY
    elif any(v == HealthStatus.UNHEALTHY for v in checks.values()):
        status = HealthStatus.UNHEALTHY
    else:
        status = HealthStatus.DEGRADED

    return Response(
        content=json.dumps({"status": status, "checks": checks}),
        status_code=200 if status == HealthStatus.HEALTHY else 503,
        media_type="application/json",
    )
```

### Kubernetes Configuration

```yaml
apiVersion: v1
kind: Pod
spec:
  containers:
  - name: app
    livenessProbe:
      httpGet:
        path: /health/live
        port: 8000
      initialDelaySeconds: 10
      periodSeconds: 15
      failureThreshold: 3
    readinessProbe:
      httpGet:
        path: /health/ready
        port: 8000
      initialDelaySeconds: 5
      periodSeconds: 10
      failureThreshold: 2
    startupProbe:
      httpGet:
        path: /health/live
        port: 8000
      failureThreshold: 30
      periodSeconds: 10
```

---

## V. Distributed Tracing

### Concepts

| Term | Definition |
|------|-----------|
| **Trace** | End-to-end journey of a request through all services |
| **Span** | Single unit of work within a trace |
| **Trace ID** | Unique identifier for the entire trace |
| **Span ID** | Unique identifier for a single span |
| **Parent Span ID** | Links child spans to their parent |
| **Context Propagation** | Passing trace context between services |

### When to Use Tracing

```
Do you have microservices?
  → YES → Tracing is essential
  → NO ↓

Do you have async/background processing?
  → YES → Tracing helps correlate request to job
  → NO ↓

Do you have complex request flows?
  → YES → Tracing reveals bottlenecks
  → NO → Logs + metrics may be sufficient
```

### OpenTelemetry Implementation

```python
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

# Setup
provider = TracerProvider()
processor = BatchSpanProcessor(OTLPSpanExporter(endpoint="http://jaeger:4317"))
provider.add_span_processor(processor)
trace.set_tracer_provider(provider)

tracer = trace.get_tracer("order-service")

# Manual spans
@app.post("/orders")
async def create_order(order: OrderCreate):
    with tracer.start_as_current_span("create_order") as span:
        span.set_attribute("order.customer_id", order.customer_id)
        span.set_attribute("order.item_count", len(order.items))

        # Create order in database
        with tracer.start_as_current_span("db_insert"):
            result = await db.insert(order)

        # Process payment
        with tracer.start_as_current_span("process_payment") as payment_span:
            payment_span.set_attribute("payment.amount", order.total)
            await payment_service.charge(order.customer_id, order.total)

        # Send confirmation
        with tracer.start_as_current_span("send_confirmation"):
            await email_service.send_confirmation(order.customer_id, result.id)

        return result

# Automatic instrumentation (FastAPI)
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
FastAPIInstrumentor.instrument_app(app)

# Database instrumentation
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
SQLAlchemyInstrumentor().instrument(engine=engine)
```

---

## VI. Alerting

### Alert Design Decision Tree

```
Should this be an alert?
  → Is someone expected to take action? → YES → Alert
  → Is it just informational? → NO → Dashboard metric

What severity?
  → User-facing impact, revenue loss → Critical (page someone)
  → Degraded performance, partial outage → Warning (notify team)
  → Approaching threshold → Info (ticket for investigation)

When to alert?
  → Error rate > 1% for 5 minutes → Critical
  → Error rate > 0.1% for 15 minutes → Warning
  → P99 latency > 2s for 5 minutes → Warning
  → Disk usage > 80% → Warning
  → Disk usage > 95% → Critical
  → Certificate expires in 30 days → Warning
  → Certificate expires in 7 days → Critical
```

### Alert Fatigue Prevention

| Rule | Implementation |
|------|----------------|
| Actionable alerts only | Every alert must have a runbook |
| Appropriate thresholds | Not too sensitive, not too lax |
| Group related alerts | Don't page for 10 separate services |
| Suppress during maintenance | Maintenance windows silence alerts |
| Regular review | Monthly alert review, remove noise |

### Alertmanager Configuration

```yaml
# alertmanager.yml
global:
  resolve_timeout: 5m

route:
  group_by: ['alertname', 'severity']
  group_wait: 30s
  group_interval: 5m
  repeat_interval: 4h
  receiver: 'slack-notifications'
  routes:
    - match:
        severity: critical
      receiver: 'pagerduty'
      repeat_interval: 1h

receivers:
  - name: 'slack-notifications'
    slack_configs:
      - channel: '#alerts'
        send_resolved: true
        title: '{{ .GroupLabels.alertname }}'
        text: '{{ .CommonAnnotations.description }}'

  - name: 'pagerduty'
    pagerduty_configs:
      - service_key: '<pagerduty-key>'
        severity: '{{ .CommonLabels.severity }}'
```

### Prometheus Alert Rules

```yaml
# prometheus-rules.yml
groups:
  - name: application
    rules:
      - alert: HighErrorRate
        expr: rate(http_requests_total{status=~"5.."}[5m]) / rate(http_requests_total[5m]) > 0.01
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "High error rate detected"
          description: "Error rate is {{ $value | humanizePercentage }} for {{ $labels.endpoint }}"
          runbook_url: "https://runbooks.example.com/high-error-rate"

      - alert: HighLatency
        expr: histogram_quantile(0.99, rate(http_request_duration_seconds_bucket[5m])) > 2
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High P99 latency"
          description: "P99 latency is {{ $value }}s for {{ $labels.endpoint }}"

      - alert: DatabaseConnectionPoolExhausted
        expr: db_connection_pool_active / db_connection_pool_size > 0.9
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "Database connection pool nearly exhausted"
          description: "Pool utilization is {{ $value | humanizePercentage }}"
```

---

## VII. Dashboard Design

### Dashboard Hierarchy

```
Level 1: Executive Dashboard
  → Business metrics (revenue, users, conversion)
  → High-level health (green/yellow/red)
  → SLA compliance

Level 2: Service Dashboard
  → RED metrics per service
  → Error rates and latency
  → Resource utilization

Level 3: Infrastructure Dashboard
  → CPU, memory, disk, network
  → Database metrics
  → Queue depths

Level 4: Debug Dashboard
  → Detailed traces
  → Log aggregation
  → Specific investigation views
```

### Dashboard Design Principles

| Principle | Implementation |
|-----------|----------------|
| **Top-down** | Most important info at top-left |
| **Consistent** | Same time ranges, same color scheme |
| **Actionable** | Every panel should answer a question |
| **Not too dense** | 6-8 panels per row, not 20 |
| **Context** | Show thresholds, not just raw numbers |
| **Comparisons** | Show current vs previous period |

### Grafana Dashboard Example

```json
{
  "panels": [
    {
      "title": "Request Rate",
      "type": "stat",
      "targets": [{
        "expr": "sum(rate(http_requests_total[5m]))",
        "legendFormat": "req/s"
      }],
      "thresholds": {
        "steps": [
          {"color": "green", "value": 0},
          {"color": "yellow", "value": 100},
          {"color": "red", "value": 500}
        ]
      }
    },
    {
      "title": "Error Rate",
      "type": "gauge",
      "targets": [{
        "expr": "rate(http_requests_total{status=~\"5..\"}[5m]) / rate(http_requests_total[5m])",
        "legendFormat": "error %"
      }],
      "thresholds": {
        "steps": [
          {"color": "green", "value": 0},
          {"color": "yellow", "value": 0.001},
          {"color": "red", "value": 0.01}
        ]
      }
    }
  ]
}
```

---

## VIII. SLI / SLO / SLA Concepts

### Definitions

| Term | Definition | Example |
|------|-----------|---------|
| **SLI** | Service Level Indicator (what you measure) | Availability, latency, error rate |
| **SLO** | Service Level Objective (what you target) | 99.9% availability, P99 < 200ms |
| **SLA** | Service Level Agreement (what you contract) | 99.5% availability, penalty for breach |

### SLI Selection Decision Tree

```
What matters most to users?
  → Can they reach the service? → Availability SLI
  → Can they complete their task? → Success rate SLI
  → How fast can they complete it? → Latency SLI

SLI = (good events / total events) × 100

Examples:
  Availability: (successful health checks / total health checks) × 100
  Success rate: (non-error responses / total responses) × 100
  Latency: (requests < 200ms / total requests) × 100
```

### Error Budget

```
SLO: 99.9% availability
Error budget: 0.1% = 43.2 minutes/month

Rules:
  → Budget remaining > 50%: Innovate freely
  → Budget remaining 20-50%: Be cautious
  → Budget remaining < 20%: Freeze non-critical changes
  → Budget exhausted: Focus on reliability only
```

### SLO Implementation

```python
# Prometheus SLO recording rules
# prometheus-rules.yml
groups:
  - name: slo
    interval: 1m
    rules:
      # SLI: Availability
      - record: slo:availability:ratio_rate5m
        expr: |
          sum(rate(http_requests_total{status!~"5.."}[5m]))
          /
          sum(rate(http_requests_total[5m]))

      # Error budget remaining (30-day window)
      - record: slo:error_budget:remaining
        expr: |
          (1 - (1 - slo:availability:ratio_rate5m) / (1 - 0.999))
          * 100

      # Alert when error budget is low
      - alert: ErrorBudgetLow
        expr: slo:error_budget:remaining < 20
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Error budget below 20%"
          description: "Only {{ $value | humanize }}% error budget remaining"
```

---

## IX. Complete Observability Checklist

### Logging

- [ ] Structured logging (JSON format)
- [ ] Correlation ID in all logs
- [ ] Appropriate log levels
- [ ] PII/redacted sensitive data
- [ ] Error stack traces captured
- [ ] Log aggregation system configured

### Metrics

- [ ] RED metrics for all services
- [ ] USE metrics for infrastructure
- [ ] Business metrics instrumented
- [ ] Custom metrics for domain-specific needs
- [ ] Prometheus/Grafana (or equivalent) configured

### Tracing

- [ ] OpenTelemetry SDK integrated
- [ ] Context propagation between services
- [ ] Database queries traced
- [ ] External HTTP calls traced
- [ ] Sampling strategy configured

### Health Checks

- [ ] Liveness endpoint implemented
- [ ] Readiness endpoint implemented
- [ ] Startup probe for slow-starting services
- [ ] Health check tests dependencies
- [ ] Kubernetes probes configured

### Alerting

- [ ] Critical alerts have runbooks
- [ ] Alert thresholds are tuned
- [ ] On-call rotation defined
- [ ] Escalation policy documented
- [ ] Alert fatigue reviewed monthly

### Dashboards

- [ ] Executive/overview dashboard
- [ ] Per-service dashboards
- [ ] Infrastructure dashboard
- [ ] Error/investigation dashboard
- [ ] SLO compliance dashboard

---

## References

- **Google SRE Book** — https://sre.google/sre-book/table-of-contents/
- **OpenTelemetry Documentation** — https://opentelemetry.io/docs/
- **Prometheus Best Practices** — https://prometheus.io/docs/practices/
- **Grafana Dashboard Design** — https://grafana.com/docs/grafana/latest/dashboards/
- **The Three Pillars of Observability** — Charity Majors, Cindy Sridharan

## Related Skills

- **service-composition** — Distributed tracing and metrics across composed services.
- **clean-code** — Structured logging and clear metric names improve debuggability.
- **pd** — Master orchestrator. Observability is set up during infrastructure phases.
- **design-patterns** — Observer pattern for event-driven monitoring and alerting.
