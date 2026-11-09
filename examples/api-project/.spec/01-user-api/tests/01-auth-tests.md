# Task: Auth utility tests

**Task:** T8
**Wave:** 4
**Status:** done

## Cases

- [x] Hash and verify the correct password.
- [x] Reject an incorrect password.
- [x] Two hashes of the same password differ (salt).
- [x] Create a token and decode it to the original subject/role.
- [x] Reject a malformed token.
- [x] Reject an expired token.
- [x] Normalize email casing before uniqueness checks.

## Evidence

```text
tests/test_auth.py ............ 12 passed
```

No test asserts a specific hash string; assert the verification behavior instead.
