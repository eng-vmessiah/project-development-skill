# Task: Endpoint and permission tests

**Task:** T9
**Wave:** 4
**Status:** done

## Cases

- [x] Register returns a token and persists the user.
- [x] Duplicate registration returns 409.
- [x] Login with valid credentials returns 200 and a token.
- [x] Login with invalid credentials returns 401.
- [x] `/users/me` without a token returns 401.
- [x] `/users/me` with a valid token returns the profile without the hash.
- [x] `PUT` and `DELETE /users/me` affect only the current user.
- [x] `GET /users` as a normal user returns 403.
- [x] `GET /users` as an admin returns a paginated list.
- [x] `PATCH /users/{id}/role` as a normal user returns 403.
- [x] Role update rejects an unknown role.

## Evidence

```text
tests/test_auth_api.py ........ 7 passed
tests/test_users_api.py ....... 11 passed
```

Every 403 case asserts that the handler did not mutate data.
