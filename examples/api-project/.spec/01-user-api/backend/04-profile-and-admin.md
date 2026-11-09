# Task: Profile, admin list, and role update

**Task:** T5/T6/T7
**Wave:** 3
**Status:** done

## Objective

Implement the authenticated profile endpoints and the admin-only user surface with
consistent errors and OpenAPI metadata.

## Acceptance

- [x] `GET /users/me` returns the current profile without `hashed_password`.
- [x] `PUT /users/me` updates only allowed fields (email, password).
- [x] `DELETE /users/me` removes the current user and returns 204.
- [x] `GET /users` requires the `admin` role and supports limit/offset.
- [x] `PATCH /users/{id}/role` requires `admin` and rejects unknown roles.
- [x] `require_admin` returns 403 before the handler runs.
- [x] Every route declares its bearer requirement in OpenAPI.

## Notes

Do not let an admin demote the last remaining admin in this example; add a guard
if the rule becomes part of the contract.
