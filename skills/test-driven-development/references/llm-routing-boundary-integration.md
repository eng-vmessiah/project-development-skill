# LLM Routing Boundary Integration Reference

Use this reference when applying a shared routing/resilience policy to an existing LLM call site.

## Adopted architecture patterns

These patterns originated in OmniRoute/OmniRouting and are adapted selectively:

- classify errors before deciding whether fallback is allowed;
- isolate circuit-breaker state by logical provider/model key;
- use explicit `closed`, `open`, and `half_open` states with deterministic clock injection in tests;
- bound attempts per turn and preserve the primary error when all routes fail;
- keep policy decisions separate from provider execution;
- preserve a future provider seam without implementing an additional provider prematurely;
- add correlation, health, LKGP, cost, capabilities, and MCP/API contracts as separate follow-up boundaries rather than coupling them into the first migration.

## Integration sequence

1. Add a focused call-site test that captures the existing externally visible contract.
2. Add a RED test for the policy distinction that matters (e.g. auth/config must not fallback).
3. Implement the smallest classifier/policy change.
4. Run the call-site test plus the policy unit tests.
5. Only then replace local primary/fallback control flow with a shared executor.
6. Re-check side effects: quota increments, persistence, canvas mutation, tool loops, and response parsing.

## Guardrails

- `401/403`, missing configuration, and unknown errors are not automatically fallback-safe.
- `429`, timeout, and upstream `5xx` are transient candidates, subject to the call site's contract.
- Invalid structured output is not necessarily the same class as a thrown provider error; preserve its existing behavior until explicitly covered.
- Do not log credentials, prompt bodies, full provider response bodies, or secret-bearing error text.
- Do not import OmniRoute as a dependency or replace the host stack; adapt the patterns to the existing architecture.
