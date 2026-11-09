# VERIFICATION.md - 01-user-api

**Status:** verified
**Date:** 2026-06-14

## Requirement coverage

| Requirement | Evidence | Result |
|---|---|---|
| R1 registration | `tests/02-endpoint-tests.md` — register/duplicate cases | pass |
| R2 login + JWT | `tests/01-auth-tests.md` — token cases; `tests/02-endpoint-tests.md` — login | pass |
| R3 profile read/update | `tests/02-endpoint-tests.md` — `/users/me` cases | pass |
| R4 account deletion | `tests/02-endpoint-tests.md` — delete case | pass |
| R5 admin list/role | `tests/02-endpoint-tests.md` — admin and 403 cases | pass |
| R6 password hashing | `tests/01-auth-tests.md` — bcrypt cases | pass |
| R7 stable errors | `tests/02-endpoint-tests.md` — 401/403/409 cases | pass |
| R8 OpenAPI auth | manual check of `/openapi.json` bearer scheme | pass |

## Known limits

- SQLite is used for the example; PostgreSQL-specific behavior is untested.
- No refresh-token or revocation path; expiry is the only invalidation.
- Rate limiting is intentionally out of scope.

## Verdict

The example's happy path and permission boundaries are verified. It is a teaching
artifact, not a production authentication service.
