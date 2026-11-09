# Task: Registration and login

**Task:** T3/T4
**Wave:** 2
**Status:** done

## Objective

Implement `POST /auth/register` and `POST /auth/login`, including bcrypt hashing,
JWT creation, and the current-user dependency.

## Acceptance

- [x] Registration rejects malformed emails and passwords shorter than 8 chars.
- [x] Duplicate email returns 409 and never creates a second user.
- [x] Passwords are hashed with bcrypt cost 12; plaintext is never stored.
- [x] Login returns a bearer token only for valid credentials.
- [x] Invalid credentials return 401 with the same message for unknown email and
      wrong password.
- [x] The current-user dependency rejects missing, malformed, and expired tokens.

## Notes

The login response and the registration response share the same token schema.
Keep the token payload minimal: `sub` (user id) and `role`.
