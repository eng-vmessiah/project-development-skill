# Task: Project skeleton and configuration

**Task:** T1
**Wave:** 1
**Status:** done

## Objective

Create the smallest FastAPI application that can run locally and in tests, with
configuration loaded from the environment and a database session dependency.

## Acceptance

- [x] `app/main.py` exposes the ASGI app.
- [x] Settings are read from environment variables with safe local defaults.
- [x] `DATABASE_URL` defaults to a local SQLite file for the example.
- [x] `GET /health` returns 200 without authentication.
- [x] Tests use an isolated database, never the developer database.

## Notes

Keep the skeleton boring: one app factory, one settings object, one session
dependency. Add routers as the feature grows instead of putting handlers in
`main.py`.
