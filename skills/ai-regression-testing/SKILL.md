---
name: ai-regression-testing
version: 1.0.0
license: MIT
description: Regression testing patterns for AI-assisted development. Sandbox/production path parity, response shape contracts, data completeness, and patterns to catch AI blind spots.
metadata:
  hermes:
    tags: [testing, regression, ai, quality, contracts]
    related_skills: [test-driven-development, systematic-debugging, requesting-code-review, pd]
---
## When to Use

- When the task matches this skill's purpose
- When explicitly requested by the user



# AI Regression Testing

Testing patterns designed for AI-assisted code generation — where the same model writes and reviews code, creating systematic blind spots.

## When to Activate

- AI agent modified API routes or backend logic
- Bug was found and fixed — need regression test
- Sandbox/mock mode exists and can be leveraged for DB-free testing
- After code review, run tests as final verification

## The Core Problem

When AI writes code and then reviews its own work, it carries the same assumptions into both steps:

```
AI writes fix → AI reviews fix → AI says "looks correct" → Bug still exists
```

**Common AI regression patterns:**

1. **Sandbox/Production path mismatch** — AI fixes one code path, forgets the other
2. **Query/response mismatch** — field added to response schema but missing from data query
3. **Response shape drift** — required fields omitted from some endpoints
4. **Optimistic update without rollback** — UI updates but no restore on failure
5. **Type safety creep** — `as any` / `@ts-ignore` suppressing type errors instead of fixing

## Test Strategy: Bug-Driven Coverage

Don't aim for 100% coverage. Test where bugs were found:

```
Bug in /api/users/profile  → Write test for profile API
Bug in /api/pets           → Write test for pets API
No bug in /api/bookings    → Don't write test (yet)
```

AI repeats the same mistake category. Once tested, that regression **cannot happen again**.

## Response Shape Contract

Define required fields contract per endpoint. Test ALL return the fields:

```typescript
// Contract: every GET /users/me MUST return these fields
const REQUIRED_FIELDS = ['id', 'name', 'email', 'avatarUrl']

describe('GET /users/me', () => {
  it('returns all required fields', async () => {
    const res = await api.get('/users/me')
    for (const field of REQUIRED_FIELDS) {
      expect(res.body).toHaveProperty(field)
    }
  })
})
```

## Route-Level Runtime Parity

A focused jsdom test with hand-rolled mocks proves the component against the shape you *believe* the API returns. It does not prove the real route. AI-written tests and code share the same assumption, so both pass while the page crashes.

1. After the focused test, render the actual route in the running app against the shared mock/backend at the contract width, not only in jsdom.
2. Install `window.addEventListener('error', ...)` and `unhandledrejection` before navigating; assert `document.getElementById('root').children.length > 0` (empty text does not distinguish an error from "loading").
3. A page that throws `Cannot read properties of undefined (reading 'find'|'length'|'emailAddress')` after a green test is usually a payload-shape mismatch: the page reads `data.items`/`data.files`/`data.threads` but the mock returns `[]`. Beware `[].keys`: it is `Array.prototype.keys` (a function), not a list, so `payload.keys.filter` fails in a different way.
4. Normalize every collection at the boundary:
   `const items = Array.isArray(data) ? data : data?.items ?? [];`
   and guard `groupBy`/`for...of` with `Array.isArray` before iterating. Do not add a fallback only after the crash; start with the union type.
5. Test both shapes in the focused test (bare array and `{items}`), so the page is robust to the API variant.
6. Make the mock mirror the server's `c.json({...})` keys exactly, not a generic `[]`; a mock with invented keys makes the preview lie as much as a missing key makes it crash.

## Data Query Completeness

Regression: AI added field to response schema but forgot to include it in the data query:

```typescript
it('response includes newly added field', async () => {
  const res = await api.get('/items')
  const items = res.body

  for (const item of items) {
    expect(item).toHaveProperty('newField')  // ← often forgotten in query
  }
})
```

## Optimistic Update Rollback

```typescript
// regression: optimistic update without rollback
it('restores previous state on API failure', async () => {
  const previousState = getState()

  await triggerAction('invalid-id')  // fails

  // State should be restored to previous
  expect(getState()).toEqual(previousState)
})
```

## Checks that pass without proving

A green check is only evidence if it fails when the thing it measures is broken. These four mechanisms
produce green while proving nothing, and all of them survive a normal test run:

1. **The pipeline hides the exit status.** `gate | tail -2 && git commit` reads the status of `tail`
   (always 0), so a red gate gets committed. Redirect instead: `cmd > /tmp/out 2>&1; echo $?`, then read
   the file; use `set -o pipefail` when a pipe is unavoidable. Same for `pytest ... | tail`.
2. **The error is printed and the code is 0.** A check built on `grep -P` with a pattern the engine
   rejects, or on `! cmd` around a command that errors, prints the failure and exits 0. Accept a check
   only when a failing fixture makes it exit non-zero **and** the passing run has empty stderr; capture
   both states.
3. **The canary is a constant, not an assertion.** `assert total == N` over an artifact that legitimately
   grows turns every addition into a red gate and trains everyone to bump the number. Assert a floor
   (`>= 60`) to prove the parser found the artifact, and let a strict parser catch silent loss.
4. **The parser absorbs a near-miss instead of refusing.** In documents with sections, content under an
   unrecognized header can be silently attached to the previous section, so the import "succeeds" with the
   wrong structure. An unknown header must close the current section, and the refusal must name the line
   plus the item left orphaned. Test the near-miss in both positions: before any section, and between two
   valid ones. A guard that only fires on the empty state proves nothing.

5. **The suite resolves the production default.** Pinning a fixture value (a temp DB path, an ephemeral signing
   key, a tmp token) makes the *value* hermetic but not the *target*: any test that lets the code fall through
   to its default workspace/DB/ledger path writes real state, now signed or sealed with the test secret. It is
   the worst kind of green — the write succeeds, the assertion passes, and the artifact can never be verified
   again by the real key (quarantine is the only repair). Grep the tests for CLI/app entry points invoked
   without an explicit `--workspace`/`--root`/`--db` argument, make the fixture chdir into `tmp_path` so every
   default resolution lands there, and add a session-level guard: snapshot the production store (path, size,
   sha256 per file) at session start and fail at `sessionfinish` if anything changed. Prove it by hashing the
   store before and after one full run of the real gate, not by reading the test file.

Rule: for every guard you add, write the fixture that must fail, run it, and paste both states. A fixture
that cannot be made to fail marks a guard that is decoration.

## Key Anti-Patterns to Scan For

1. **State mutation before API response** — `setState(data)` then `await api.post(...)`. If API fails, state is wrong.
2. **as any / @ts-ignore in new code** — check that they're justified, not laziness.
3. **SELECT * changed** — if schema changed, did query update too?
4. **Error handling gaps** — `.catch(() => {})` or missing rollback paths.

## DO / DON'T

**DO:**
- Write test immediately after finding a bug (before fixing if possible)
- Test API response shape, not implementation
- Name tests after the bug: `(regression R1: missing isForAdoption)`
- Keep tests fast (< 1s each, no DB needed)

**DON'T:**
- Write tests for code that never had a bug
- Trust AI self-review as substitute for automated tests
- Aim for coverage % — aim for regression prevention

## Related Skills

- **test-driven-development** — TDD discipline. Write failing tests before fixes to prove the bug exists and prevent regression.
- **systematic-debugging** — Root-cause debugging. Regression tests are created after finding the root cause.
- **requesting-code-review** — Pre-commit verification. Regression tests are checked as part of the quality gate.
- **pd** — Master orchestrator. Regression testing is part of Phase 5 (Testing) in the PD pipeline.
