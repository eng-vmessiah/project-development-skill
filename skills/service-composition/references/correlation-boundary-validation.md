# Correlation Boundary Validation Reference

Use this reference when wiring an HTTP backend to a worker/container such as a Node-based worker host.

## Contract

- Validate bounded `X-Request-Id` and `X-Trace-Id` at the ingress boundary.
- Generate missing/invalid IDs; derive `traceId` from `requestId` when absent.
- Keep IDs stable across retries; track retry attempt separately.
- Store IDs in request-scoped ALS for local logging, then explicitly copy them into downstream headers.
- Return correlation IDs in response headers.
- Never include prompts, user content, tokens, credentials, or raw provider errors in correlation metadata.

## Implementation pattern

1. Add a pure `correlation-context` module with deterministic validation and generated fallback behavior.
2. Add `REQ_ID_STORAGE` and `TRACE_ID_STORAGE` to the logger/context layer.
3. Expose a single `getCorrelationHeaders()` helper; do not duplicate ALS reads in every route.
4. Apply the helper at every backend-to-worker `fetch` boundary, including GET, JSON POST, multipart/media, SSE handshake, scheduler, admin, and proxy calls.
5. For retries, do not regenerate IDs; increment only the attempt field in structured metadata.

## Sibling container propagation (worker-host pattern)

When the worker process (e.g. worker host) spawns an isolated container (e.g. Docker sibling), the correlation IDs must travel into the container as **env vars**, not headers — containers don't receive HTTP headers at spawn time.

The full loop:

1. **Backend → worker host (HTTP):** Backend sends `X-Request-Id` / `X-Trace-Id` headers on every request to the worker host's HTTP server (onboarding-server, webhook, etc.).
2. **worker host (extract + ALS):** The HTTP request handler extracts the headers and runs the request body inside `runWithCorrelation(ids, handler)` so all descendant async operations can read the IDs via `getCorrelationIds()`.
3. **worker host → spawn (env vars):** `buildContainerArgs()` calls `getCorrelationIds()` and, when present, adds `-e APP_REQUEST_ID=<id>` and `-e APP_TRACE_ID=<id>` to the Docker run command. When absent (host-sweep, polling), the env vars are omitted — the container runs without correlation context.
4. **Container → backend (MCP HTTP headers):** The MCP server inside the container reads `APP_REQUEST_ID` / `APP_TRACE_ID` from `process.env` at module load and includes them as `X-Request-Id` / `X-Trace-Id` headers in every `fetch()` back to the backend. Use spread with conditional: `...(REQUEST_ID ? { 'X-Request-Id': REQUEST_ID } : {})` so absent IDs don't produce empty headers.
5. **Backend (receive + propagate):** The backend's ingress middleware already accepts and propagates these headers, closing the loop. The same `requestId`/`traceId` appears in logs across all four hops.

Key properties:
- The container's `correlation-context.ts` is deliberately standalone — it does not import the backend's module. Each process owns its own ALS.
- `extractCorrelationFromHeaders` returns `null` for array-type headers, missing headers, or empty strings. This prevents garbage from leaking into env vars.
- The `runWithCorrelation` wrapper is applied after auth check but before the route handler — auth failures (401) correctly omit correlation from logs.

## Batch telemetry writer with graceful shutdown

When multiple call sites emit usage events, prefer an async batch writer over synchronous DB writes:

1. **Queue + batch flush:** `enqueueLlmUsageEvent(event)` pushes to an in-memory queue (bounded, e.g. max 100). A scheduled flush runs every ~1s, writing batches of ~25 to the DB via `Promise.allSettled`.
2. **Idempotent persistence:** `ON CONFLICT(event_id) DO NOTHING` so retries or duplicate enqueues are safe.
3. **Graceful shutdown:** Register a `createGracefulShutdown(server, { flushLlmUsageEvents, exit })` on `SIGTERM`/`SIGINT`. The handler: closes the HTTP server (stops accepting new requests), flushes the queue, then exits. If flush fails, exit anyway — the queue is volatile by design.
4. **Injection for testing:** The shutdown handler accepts `flushLlmUsageEvents` and `exit` as injected deps, making it testable without process manipulation.
5. **Guard against double-invocation:** Use a `shuttingDown` flag so a second SIGTERM doesn't re-enter the handler.

Pitfall: each call site must catch telemetry failures locally — `enqueueLlmUsageEvent` is synchronous (push to array), so it won't throw under normal conditions, but if the queue is full it silently drops. This is by design: telemetry must never block the user-facing response.

## Multi-tenant aggregation scoping

When exposing aggregated telemetry data via HTTP:

1. Scope SQL by `user_id = ?` — never expose other tenants' data.
2. Support optional date range filtering (`from` / `to` query params) by appending conditions to the WHERE clause.
3. Group by `provider, model` with `SUM()` for token counts and `CASE WHEN outcome = 'success' THEN 1 ELSE 0 END` for success/failed counts.
4. Test multi-tenant isolation explicitly: assert that the SQL args contain the authenticated user's ID and do not contain other users' IDs.

## TDD and verification

For each new boundary:

1. Write a test that runs the real client/route with mocked transport inside both ALS stores.
2. Assert `X-Request-Id` and `X-Trace-Id` on the outbound request, while preserving auth/content-type/user headers.
3. Run the focused route slice and TypeScript build.
4. Run `git diff --check`.
5. Run the complete backend suite after the boundary batch; record file/test totals in the plan checkpoint.

For sibling container correlation:

1. Test the `correlation-context` module in isolation (8 tests: null outside context, available inside, null after exit, async propagation, header extraction valid/missing/single/array).
2. Verify the existing `container-runner.test.ts` still passes (the env var injection is conditional and additive).
3. Worker suite may have pre-existing import errors in WSL (missing `@google/generative-ai`, `busboy` types) — these are environment-dependent, not regressions.

For batch writer migration:

1. When migrating call sites from `persistLlmUsageEvent` (sync import) to `enqueueLlmUsageEvent` (batch import), update test mocks: change `vi.mock('../lib/llm-telemetry.js', ...)` to `vi.mock('../lib/llm-telemetry-writer.js', ...)`, rename the mock from `persistLlmUsageEvent` to `enqueueLlmUsageEvent`, and change `mockRejectedValueOnce` (async) to `mockImplementationOnce(() => { throw new Error(...) })` (sync throw — enqueue is synchronous, not async).

## Pitfalls

- Testing a route through a standalone Hono app may bypass the global ingress middleware; seed ALS explicitly in the boundary test.
- A test that only checks existing behavior or status codes does not prove propagation; inspect the mocked transport headers.
- Inline header replacements can accidentally drop `Content-Type`, `Authorization`, `X-User-Id`, or caller-supplied headers. Merge, do not replace.
- Do not mark a whole phase complete while sibling-container reception/preservation or retry-attempt semantics remain untested.
- `await persistLlmUsageEvent(...)` → `enqueueLlmUsageEvent(...)` migration drops the `await`. Leaving `await` on a synchronous function is harmless, but test assertions using `mockRejectedValueOnce` will silently fail because the mock never rejects — use `mockImplementationOnce(() => { throw new Error(...) })` instead.
- When a call site uses `chatCompletion` inside a `for` loop (e.g. agent tool-call rounds), the completion variable is loop-scoped. To use it in telemetry after the loop, declare `let lastCompletion: ChatCompletionResponse | null = null` before the loop and assign `lastCompletion = completion` after each call.