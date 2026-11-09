# SPEC.md - 01-user-api

**Feature:** User API with JWT authentication
**Example:** REST API with FastAPI
**Created:** 2026-06-14

## Requirements

- [x] R1. A user can register with a unique email and a password.
- [x] R2. A user can log in and receive a short-lived JWT access token.
- [x] R3. An authenticated user can read and update their own profile.
- [x] R4. An authenticated user can delete their own account.
- [x] R5. An admin can list users and change their role.
- [x] R6. Passwords are stored only as bcrypt hashes.
- [x] R7. Errors use stable HTTP status codes and do not leak secrets.
- [x] R8. The OpenAPI schema documents every endpoint and auth requirement.

## Endpoints

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/auth/register` | none | Create a user and return a token |
| POST | `/auth/login` | none | Exchange credentials for a token |
| GET | `/users/me` | bearer | Read the current profile |
| PUT | `/users/me` | bearer | Update the current profile |
| DELETE | `/users/me` | bearer | Delete the current account |
| GET | `/users` | admin | List users with pagination |
| PATCH | `/users/{id}/role` | admin | Change a user's role |

## Data model

`users`

| Column | Type | Notes |
|---|---|---|
| `id` | UUID string | primary key |
| `email` | string | unique, indexed, normalized lowercase |
| `hashed_password` | string | bcrypt cost 12 |
| `role` | string | `user` or `admin` |
| `created_at` | timestamp | server default |
| `updated_at` | timestamp | updated on change |

## Non-goals

- Email verification and password reset.
- OAuth/social login.
- Refresh-token rotation and server-side revocation.
- Multi-tenant or organization-level roles.

## Success criteria

- [x] The happy path and each permission boundary have an integration test.
- [x] A non-admin cannot list users or change roles.
- [x] No response body contains `hashed_password`.
