# PLAN.md - 01-user-api

**Feature:** User API with JWT authentication
**Waves:** 4
**Tasks:** 9

## Wave 1: Foundation

- [x] T1. Create the FastAPI project skeleton and configuration.
- [x] T2. Create the `User` model and database session dependency.

## Wave 2: Authentication

- [x] T3. Implement registration, login, and bcrypt hashing.
- [x] T4. Add JWT creation/validation and the bearer dependency.

## Wave 3: User surface

- [x] T5. Implement `GET/PUT/DELETE /users/me`.
- [x] T6. Implement admin list and role update endpoints.
- [x] T7. Add consistent error handling and OpenAPI metadata.

## Wave 4: Verification

- [x] T8. Add auth utility and integration tests.
- [x] T9. Add permission-boundary tests for every admin endpoint.

## Exit criteria

- [x] All endpoint tests pass.
- [x] `GET /users` returns 403 for a normal user.
- [x] The OpenAPI document lists the bearer requirement.
- [x] `VERIFICATION.md` maps each requirement to a test.
