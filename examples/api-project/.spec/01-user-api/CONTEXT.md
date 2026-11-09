# CONTEXT.md - 01-user-api

## Decisions

### D-001: JWT access tokens (accepted)

Use a signed JWT with a short expiry. The token contains the user id and role;
no password or personal data is embedded. Revocation is out of scope for this
example, so the token lifetime is deliberately short.

### D-002: bcrypt cost 12 (accepted)

Hash passwords with bcrypt via `passlib`. Never log or return the hash. Compare
using the library's constant-time verification, not string equality.

### D-003: UUID primary key (accepted)

Use UUID v4 strings rather than sequential integers. The id appears in tokens and
URLs; UUIDs avoid exposing user counts or enabling trivial enumeration.

### D-004: Role check at the dependency boundary (accepted)

A single `require_admin` dependency enforces the role before a handler runs. This
keeps authorization out of individual handlers and makes the 403 path testable in
one place.

## Trade-offs

- No refresh token: simpler, but users must log in again after expiry.
- No email verification: registration is fast, but the example does not prove
  ownership of the email.
- SQLite by default: easy to run locally; production would use PostgreSQL.

## Deferred

- Email verification, password reset, refresh tokens, and OAuth.
- Rate limiting and account lockout.
- Audit log for role changes.
