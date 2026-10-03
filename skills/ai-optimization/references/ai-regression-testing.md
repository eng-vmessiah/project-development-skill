---
name: ai-regression-testing
description: Regression testing patterns for AI-assisted development. Sandbox/production path parity, response shape contracts, data completeness, and patterns to catch AI blind spots.
---

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
