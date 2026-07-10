---
name: security-checklist
description: "Security checklist covering OWASP Top 10, input validation, authentication bypass, secrets management, CORS, CSP, injection prevention, XSS, CSRF, rate limiting, password hashing, session management, and dependency scanning. Use when building or auditing secure applications."
version: 1.0.0
license: MIT
metadata:
  hermes:
    tags: [security, owasp, xss, csrf, sql-injection, authentication, secrets]
    related_skills: [auth-patterns, requesting-code-review, pd, clean-code]
---

# Security Checklist

## Overview

Security is not a feature — it's a requirement. Every application handles data that someone cares about. This skill provides a comprehensive, actionable checklist for building secure applications, organized by threat category with concrete mitigations.

**Core principle:** Security is everyone's responsibility. Developers are the first line of defense.

## When to Use

- Building any application that handles user data
- Conducting a security review or audit
- Setting up authentication and authorization
- Preparing for a penetration test
- Hardening a production application
- Onboarding new developers (security awareness)

**Don't skip for:**
- "It's just an internal tool" — internal tools get breached too
- "We'll add security later" — retrofitting is 10x harder
- "It's a prototype" — prototypes get deployed

---

## I. OWASP Top 10 (2021) Mitigations

### A01: Broken Access Control

**Threat:** Users accessing resources they shouldn't.

| Mitigation | Implementation |
|-----------|----------------|
| Deny by default | All endpoints require authentication unless explicitly public |
| Use server-side checks | Never rely on client-side access control |
| Directory listing disabled | Web server configuration |
| Log access failures | Alert on repeated unauthorized attempts |
| Rate limit API access | Prevent brute-force enumeration |

```python
# BAD: Client-side check only
@app.get("/users/{user_id}")
async def get_user(user_id: int):
    # This user_id comes from the URL — no auth check!
    return await db.get(User, user_id)

# GOOD: Server-side authorization check
@app.get("/users/{user_id}")
async def get_user(user_id: int, current_user: User = Depends(get_current_user)):
    if current_user.id != user_id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Forbidden")
    return await db.get(User, user_id)
```

### A02: Cryptographic Failures

**Threat:** Sensitive data exposed due to weak encryption.

| Mitigation | Implementation |
|-----------|----------------|
| TLS everywhere | HTTPS only, HSTS headers |
| Encrypt data at rest | Database encryption, disk encryption |
| Never store secrets in code | Use environment variables, vault |
| Use strong algorithms | AES-256, RSA-2048+, bcrypt/argon2 for passwords |
| Secure key management | Rotate keys, use KMS |

```python
# Password hashing — NEVER use MD5/SHA for passwords
from passlib.context import CryptContext

pwd_context = CryptContext(
    schemes=["argon2", "bcrypt"],
    deprecated="auto",
    argon2__memory_cost=65536,  # 64MB
    argon2__time_cost=3,
    argon2__parallelism=4,
    bcrypt__rounds=12,
)

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(password: str, hashed: str) -> bool:
    return pwd_context.verify(password, hashed)
```

### A03: Injection

**Threat:** Untrusted data sent to interpreters (SQL, NoSQL, OS, LDAP).

```python
# BAD: SQL Injection
query = f"SELECT * FROM users WHERE name = '{user_input}'"
# User input: "'; DROP TABLE users; --"

# GOOD: Parameterized query
query = "SELECT * FROM users WHERE name = %s"
cursor.execute(query, (user_input,))

# GOOD: ORM (SQLAlchemy)
user = session.query(User).filter(User.name == user_input).first()

# BAD: Command injection
os.system(f"ping {hostname}")
# User input: "localhost; rm -rf /"

# GOOD: Use subprocess with argument list
subprocess.run(["ping", "-c", "1", hostname], capture_output=True)

# BAD: LDAP injection
filter_str = f"(uid={user_input})"
# User input: "*)(objectClass=*))(|(uid=*"

# GOOD: Escape LDAP special characters
import ldap
safe_input = ldap.filter.escape_filter_chars(user_input)
filter_str = f"(uid={safe_input})"
```

### A04: Insecure Design

**Threat:** Architectural flaws that can't be fixed by implementation.

| Mitigation | Implementation |
|-----------|----------------|
| Threat modeling | STRIDE analysis for each component |
| Secure design patterns | Use proven patterns, don't invent |
| Defense in depth | Multiple layers of security |
| Separate tenants | Multi-tenant isolation |
| Limit resource usage | Rate limiting, quotas, timeouts |

### A05: Security Misconfiguration

**Threat:** Default configs, unnecessary features, verbose errors.

```python
# BAD: Verbose error messages in production
@app.exception_handler(Exception)
async def handler(request, exc):
    return JSONResponse(
        status_code=500,
        content={"error": str(exc), "traceback": traceback.format_exc()}
    )

# GOOD: Generic error messages in production
@app.exception_handler(Exception)
async def handler(request, exc):
    logger.exception("Unhandled exception")
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "request_id": request.state.request_id}
    )

# Security headers
@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "0"  # Deprecated, but harmless
    response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response
```

### A06: Vulnerable and Outdated Components

**Threat:** Using libraries with known vulnerabilities.

| Mitigation | Implementation |
|-----------|----------------|
| Dependency scanning | Dependabot, Snyk, safety, npm audit |
| Automated updates | Renovate bot, Dependabot PRs |
| Inventory tracking | Software Bill of Materials (SBOM) |
| Monitor CVEs | Subscribe to security advisories |
| Test dependencies | Run security tests in CI/CD |

```bash
# Python
pip-audit                    # Audit installed packages
safety check                 # Check for known vulnerabilities
bandit -r .                  # Static security analysis

# Node.js
npm audit                    # Check for known vulnerabilities
npx snyk test                # Snyk vulnerability scan

# Go
govulncheck ./...            # Official Go vulnerability checker

# CI/CD integration
# Add to GitHub Actions workflow:
- name: Security scan
  run: |
    pip install pip-audit bandit
    pip-audit
    bandit -r src/ -ll
```

### A07: Identification and Authentication Failures

**Threat:** Compromised authentication mechanisms.

```python
# Mitigation checklist:
# 1. Implement account lockout
# 2. Use MFA where possible
# 3. Enforce strong password policies
# 4. Generate session IDs with crypto-random
# 5. Limit login attempts
# 6. Invalidate sessions on logout

from datetime import datetime, timedelta

class LoginAttemptTracker:
    def __init__(self, redis_client):
        self.redis = redis_client
        self.max_attempts = 5
        self.lockout_duration = timedelta(minutes=15)

    async def check_and_record(self, username: str, success: bool) -> bool:
        key = f"login_attempts:{username}"

        if success:
            await self.redis.delete(key)
            return True

        attempts = await self.redis.incr(key)
        await self.redis.expire(key, int(self.lockout_duration.total_seconds()))

        if attempts >= self.max_attempts:
            return False  # Account locked
        return True
```

### A08: Software and Data Integrity Failures

**Threat:** Code or infrastructure compromised without detection.

| Mitigation | Implementation |
|-----------|----------------|
| Code signing | Verify package integrity (checksums) |
| CI/CD pipeline security | Signed commits, protected branches |
| Dependency verification | Lock files, checksums |
| Deserialization safety | Never deserialize untrusted data |
| Integrity monitoring | File integrity checks (AIDE, Tripwire) |

```python
# BAD: Deserializing untrusted data
import pickle
data = pickle.loads(user_input)  # Remote code execution!

# GOOD: Use safe serialization formats
import json
data = json.loads(user_input)  # Safe for JSON

# For binary data, use MessagePack or Protocol Buffers
# Never pickle, marshal, or yaml.load() untrusted data
```

### A09: Security Logging and Monitoring Failures

**Threat:** Inability to detect or respond to attacks.

```python
# What to log (security events):
SECURITY_EVENTS = {
    "login_success": {"level": "info", "include": ["user_id", "ip", "user_agent"]},
    "login_failure": {"level": "warn", "include": ["username", "ip", "user_agent"]},
    "password_change": {"level": "info", "include": ["user_id", "ip"]},
    "permission_denied": {"level": "warn", "include": ["user_id", "resource", "ip"]},
    "rate_limit_hit": {"level": "warn", "include": ["ip", "endpoint", "limit"]},
    "injection_attempt": {"level": "error", "include": ["ip", "endpoint", "payload_hash"]},
}

# Structured security logging
import structlog

logger = structlog.get_logger("security")

async def log_security_event(event_type: str, **kwargs):
    event_config = SECURITY_EVENTS.get(event_type)
    if not event_config:
        return

    log_data = {
        "event": event_type,
        "timestamp": datetime.utcnow().isoformat(),
        **{k: kwargs.get(k) for k in event_config["include"]},
    }

    getattr(logger, event_config["level"])(**log_data)
```

### A10: Server-Side Request Forgery (SSRF)

**Threat:** Application making requests to unintended locations.

```python
# BAD: Fetching user-provided URLs
import requests

async def fetch_url(url: str):
    return requests.get(url)  # Attacker can access internal services!

# GOOD: Validate and restrict URLs
from urllib.parse import urlparse
import ipaddress

BLOCKED_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),  # Link-local
    ipaddress.ip_network("::1/128"),  # IPv6 loopback
]

ALLOWED_SCHEMES = {"http", "https"}
BLOCKED_PORTS = {22, 25, 53, 80, 443, 3306, 5432, 6379, 27017}

async def safe_fetch(url: str):
    parsed = urlparse(url)

    if parsed.scheme not in ALLOWED_SCHEMES:
        raise ValueError(f"Invalid scheme: {parsed.scheme}")

    # Resolve hostname and check IP
    import socket
    try:
        ip = ipaddress.ip_address(socket.gethostbyname(parsed.hostname))
    except (socket.gaierror, ValueError):
        raise ValueError("Invalid hostname")

    for network in BLOCKED_NETWORKS:
        if ip in network:
            raise ValueError(f"Access to {network} is forbidden")

    return await httpx.get(url, timeout=5.0)
```

---

## II. Input Validation

### Validation Decision Tree

```
Is the input from an external source?
  → YES → Validate and sanitize
  → NO → Still validate (defense in depth)

What type of input?
  → String → Whitelist allowed characters, max length
  → Number → Range validation, type check
  → Email → Regex validation, max length
  → URL → Scheme whitelist, no SSRF
  → File → Type validation, size limit, content scan
  → HTML → Sanitize (DOMPurify, bleach)

Where to validate?
  → API boundary → Validate all incoming data
  → Database boundary → Constraints as safety net
  → UI boundary → Client-side for UX, server-side for security
```

### Validation Patterns

```python
from pydantic import BaseModel, Field, validator
import re

class CreateUserRequest(BaseModel):
    name: str = Field(
        ..., min_length=1, max_length=100,
        pattern=r"^[a-zA-Z\s'-]+$"
    )
    email: str = Field(..., max_length=255)
    age: int = Field(..., ge=0, le=150)
    bio: str = Field(None, max_length=500)

    @validator("email")
    def validate_email(cls, v):
        # RFC 5322 simplified
        pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
        if not re.match(pattern, v):
            raise ValueError("Invalid email format")
        return v.lower()

    @validator("name")
    def sanitize_name(cls, v):
        # Strip and normalize whitespace
        return " ".join(v.split())

class FileUpload(BaseModel):
    filename: str
    content_type: str
    size: int

    @validator("content_type")
    def validate_content_type(cls, v):
        allowed = {"image/jpeg", "image/png", "image/webp"}
        if v not in allowed:
            raise ValueError(f"File type {v} not allowed")
        return v

    @validator("size")
    def validate_size(cls, v):
        max_size = 10 * 1024 * 1024  # 10MB
        if v > max_size:
            raise ValueError(f"File too large (max {max_size} bytes)")
        return v
```

### Sanitization Patterns

```python
import bleach

# HTML sanitization (for user-generated content)
ALLOWED_TAGS = ["b", "i", "u", "em", "strong", "a", "p", "br", "ul", "ol", "li"]
ALLOWED_ATTRS = {"a": ["href", "title"]}

def sanitize_html(html: str) -> str:
    return bleach.clean(
        html,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRS,
        strip=True,
    )

# SQL injection prevention (parameterized queries)
# Use ORM or parameterized queries — NEVER string concatenation

# Command injection prevention
import subprocess

def safe_command(user_input: str):
    # Use argument list, not string
    result = subprocess.run(
        ["grep", "-r", user_input, "/path/to/search"],
        capture_output=True,
        text=True,
    )
    return result.stdout
```

---

## III. CORS Configuration

### CORS Decision Tree

```
Who are your API consumers?
  → Same origin only → Strict CORS (same origin)
  → Known frontend domains → Whitelist specific origins
  → Public API → Careful with credentials

Do you need cookies/auth?
  → YES → Set credentials: true + specific origins
  → NO → Can use wildcard more safely

What methods need to be exposed?
  → GET, POST only → Minimal methods
  → Full REST → GET, POST, PUT, PATCH, DELETE
```

### CORS Implementation

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# GOOD: Specific origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://app.example.com",
        "https://staging.example.com",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
    expose_headers=["X-Request-ID"],
    max_age=600,  # Cache preflight for 10 minutes
)

# BAD: Wildcard with credentials (DO NOT DO THIS)
# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["*"],  # DANGEROUS with credentials!
#     allow_credentials=True,
# )
```

---

## IV. Content Security Policy (CSP)

### CSP Implementation

```python
@app.middleware("http")
async def csp_header(request, call_next):
    response = await call_next(request)

    csp_directives = {
        "default-src": "'self'",
        "script-src": "'self' 'nonce-{random}'",
        "style-src": "'self' 'unsafe-inline'",
        "img-src": "'self' data: https:",
        "font-src": "'self'",
        "connect-src": "'self' https://api.example.com",
        "frame-ancestors": "'none'",
        "form-action": "'self'",
        "base-uri": "'self'",
    }

    csp = "; ".join(f"{k} {v}" for k, v in csp_directives.items())
    response.headers["Content-Security-Policy"] = csp

    return response
```

---

## V. Session Management

### Session Security Checklist

```python
# 1. Generate cryptographically secure session IDs
import secrets

session_id = secrets.token_urlsafe(32)  # 256 bits

# 2. Set secure cookie flags
from fastapi import Response

response.set_cookie(
    key="session_id",
    value=session_id,
    httponly=True,      # Not accessible via JavaScript
    secure=True,        # HTTPS only
    samesite="lax",     # CSRF protection
    max_age=3600,       # 1 hour expiry
    domain=".example.com",
    path="/",
)

# 3. Invalidate sessions on logout
@app.post("/logout")
async def logout(response: Response, session: Session = Depends(get_session)):
    await invalidate_session(session.id)
    response.delete_cookie("session_id")

# 4. Regenerate session ID after login
@app.post("/login")
async def login(response: Response, credentials: LoginRequest):
    user = await authenticate(credentials)
    new_session_id = secrets.token_urlsafe(32)
    await create_session(new_session_id, user.id)
    response.set_cookie("session_id", new_session_id, httponly=True, secure=True)
```

---

## VI. Dependency Scanning

### CI/CD Integration

```yaml
# .github/workflows/security.yml
name: Security Scan

on: [push, pull_request]

jobs:
  security:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install pip-audit bandit safety

      - name: Audit dependencies
        run: pip-audit

      - name: Static security analysis
        run: bandit -r src/ -ll

      - name: Check for known vulnerabilities
        run: safety check --full-report
        continue-on-error: true  # Advisory, not blocking
```

### Dependency Management Rules

| Rule | Implementation |
|------|----------------|
| Pin versions | `requests==2.31.0` not `requests>=2.0` |
| Lock files | `poetry.lock`, `package-lock.json`, `go.sum` |
| Regular updates | Weekly dependency updates |
| Security advisories | Enable Dependabot/Renovate alerts |
| SBOM generation | Track all components for compliance |

---

## VII. Security Headers Summary

```python
SECURITY_HEADERS = {
    "Strict-Transport-Security": "max-age=63072000; includeSubDomains; preload",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "X-XSS-Protection": "0",  # Deprecated, CSP is better
    "Content-Security-Policy": "default-src 'self'",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Cache-Control": "no-store, no-cache, must-revalidate",
    "Pragma": "no-cache",
}
```

---

## VIII. Complete Security Checklist

### Before Development

- [ ] Threat model completed (STRIDE for each component)
- [ ] Security requirements documented
- [ ] Dependencies reviewed and approved
- [ ] Development environment secured

### During Development

- [ ] All input validated (whitelist approach)
- [ ] All queries parameterized (no string concatenation)
- [ ] Authentication on all endpoints (except explicitly public)
- [ ] Authorization checks on every resource access
- [ ] Passwords hashed with bcrypt/argon2 (never MD5/SHA)
- [ ] Secrets in environment variables (never in code)
- [ ] Session IDs cryptographically random
- [ ] Cookies set with httponly, secure, samesite
- [ ] CORS configured with specific origins
- [ ] CSP header implemented
- [ ] Error messages don't leak internals
- [ ] Logging captures security events

### Before Deployment

- [ ] HTTPS enforced (HSTS header)
- [ ] Security headers in place
- [ ] Rate limiting configured
- [ ] Dependency scan passed
- [ ] No secrets in version control
- [ ] Database access restricted
- [ ] Admin interfaces not publicly exposed
- [ ] Backup and recovery tested

### After Deployment

- [ ] Monitoring and alerting active
- [ ] Security event logging verified
- [ ] Penetration test scheduled
- [ ] Incident response plan documented
- [ ] Regular security reviews scheduled

---

## References

- **OWASP Top 10 (2021)** — https://owasp.org/Top10/
- **OWASP Cheat Sheet Series** — https://cheatsheetseries.owasp.org/
- **CWE/SANS Top 25** — https://cwe.mitre.org/top25/
- **NIST Cybersecurity Framework** — https://www.nist.gov/cyberframework
- **SANS Secure Coding Practices** — https://www.sans.org/secure-coding/

## Related Skills

- **auth-patterns** — JWT, OAuth, and session patterns for secure authentication.
- **requesting-code-review** — Pre-commit security scan catches vulnerabilities early.
- **pd** — Master orchestrator. Security is checked throughout the PD pipeline.
- **clean-code** — Clean code reduces attack surface and improves auditability.
