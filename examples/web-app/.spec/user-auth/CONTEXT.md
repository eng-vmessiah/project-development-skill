# Context: User Authentication

**Feature:** User Authentication System
**Created:** 2026-06-14
**Status:** Active

## Architecture Decisions

### ADR-001: JWT over Session-Based Authentication

**Status:** Accepted

**Context:** We need to choose an authentication mechanism for TaskFlow. The app will potentially scale horizontally across multiple servers.

**Decision:** Use JSON Web Tokens (JWT) for authentication.

**Rationale:**
- Stateless: no session storage needed on the server
- Scales horizontally without shared session state
- Works well with mobile clients and SPAs
- Standard format, well-supported across ecosystems

**Consequences:**
- Cannot invalidate tokens server-side without a blacklist
- Token size is larger than session IDs
- Must handle token refresh strategy (deferred to Phase 2)

### ADR-002: bcrypt for Password Hashing

**Status:** Accepted

**Context:** We need to securely store user passwords.

**Decision:** Use bcrypt with cost factor 12 via the `passlib` library.

**Rationale:**
- Battle-tested algorithm, resistant to rainbow tables and brute force
- Cost factor 12 provides ~250ms hash time (good UX vs security balance)
- `passlib` provides a clean Python API
- Built-in salt generation

**Consequences:**
- Password hashing adds ~250ms to registration and login
- Must not store plaintext passwords under any circumstances
- Migration to argon2 possible later if needed

### ADR-003: UUID for Primary Keys

**Status:** Accepted

**Context:** User IDs will be exposed in JWTs and API responses.

**Decision:** Use UUID v4 as the primary key for User model.

**Rationale:**
- No sequential ID leakage (users can't guess other user IDs)
- Globally unique, no collision risk
- Works well with distributed databases
- No information leakage about user count

**Consequences:**
- Slightly larger storage than integer PKs
- Index performance slightly lower than integer PKs (acceptable for user table)
- Cannot use ID-based ordering (use created_at instead)

### ADR-004: In-Memory Rate Limiting

**Status:** Accepted (Temporary)

**Context:** We need rate limiting on auth endpoints to prevent abuse.

**Decision:** Start with in-memory rate limiting, upgrade to Redis later.

**Rationale:**
- Simple to implement, no external dependencies
- Sufficient for single-server deployment
- Can be swapped for Redis-based limiting in Phase 2

**Consequences:**
- Rate limits reset on server restart
- Cannot share limits across multiple server instances
- Must upgrade before horizontal scaling

## Constraints

### Technical
- Python 3.10+ required
- FastAPI framework (already chosen for the project)
- PostgreSQL database (already provisioned)
- SQLAlchemy ORM (already in use)

### Business
- No email verification in MVP (reduces scope)
- No OAuth/social login (can add later)
- No MFA (can add later)

### Security
- Passwords must never appear in logs, responses, or error messages
- JWT secret key must be stored in environment variables, not code
- All auth endpoints must use HTTPS in production
- Error messages must not reveal whether an email exists (use generic "invalid credentials")

## Open Questions

1. Should we implement refresh tokens in this phase or defer to Phase 2?
   - **Decision:** Defer — adds complexity, MVP works without it
2. How should we handle CORS for the frontend?
   - **Decision:** Configure in FastAPI middleware, whitelist frontend origin
3. Should rate limiting apply per-endpoint or globally?
   - **Decision:** Per-endpoint (register and login have different thresholds)

## References

- [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)
- [JWT Best Practices (RFC 8725)](https://datatracker.ietf.org/doc/html/rfc8725)
- [FastAPI Security Documentation](https://fastapi.tiangolo.com/tutorial/security/)
- [bcrypt Documentation](https://pypi.org/project/bcrypt/)
