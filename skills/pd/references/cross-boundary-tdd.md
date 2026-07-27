# Cross-boundary TDD reference

For long-running backend resilience work:

1. Keep the repository-native plan/checkpoints as the state spine when the project already has one.
2. For every boundary, write a focused RED test that inspects the actual outbound request or persisted record, not only a regression suite.
3. Apply shared context helpers (`requestId`, `traceId`, `attempt`) at the boundary while preserving auth and payload contracts.
4. For durable telemetry, test in layers: safe event builder → idempotent persistence → migration schema → call-site integration → full suite.
5. Treat telemetry failure as non-blocking unless the product contract explicitly requires otherwise.
6. After each vertical slice, run focused tests, TypeScript build, `git diff --check`, then the complete suite when schema/global infrastructure changes.
7. A passing checkpoint is an intermediate state; on a standing "continue" request, immediately start the next unblocked task instead of ending after documentation.

## Sync→async batch migration (telemetry)

When migrating call sites from direct persistence (`persistLlmUsageEvent`) to a batch writer (`enqueueLlmUsageEvent`), ALL three must change together in each test file:

1. **Hoisted mock name**: `persistLlmUsageEvent: vi.fn()` → `enqueueLlmUsageEvent: vi.fn()`
2. **Mock target module**: `vi.mock('../lib/llm-telemetry.js', ...)` → `vi.mock('../lib/llm-telemetry-writer.js', ...)`
3. **Assertions**: `mocks.persistLlmUsageEvent` → `mocks.enqueueLlmUsageEvent` (all references)

Pitfalls:
- Missing the mock target module path change: the test imports the wrong module and the mock never intercepts the call.
- Using `mockRejectedValueOnce` for a sync function: `enqueueLlmUsageEvent` is sync (void return), so rejections don't apply. Use `mockImplementationOnce(() => { throw new Error(...) })` instead.
- The `llm-usage.js` mock may also export `persistLlmUsageEvent` as a passthrough — remove it from that mock and move it to the `llm-telemetry-writer.js` mock only.

## Graceful shutdown flush hook

A batch telemetry system needs a shutdown hook to drain its queue before the process exits. Test it in isolation:

```typescript
// Create a factory that accepts injectable deps (flush + exit)
const shutdown = createGracefulShutdown(server, {
  flushLlmUsageEvents: mockFlush,
  exit: mockExit,  // Never call real process.exit in tests
});
```

Required test cases:
- Closes server + flushes + exits 0 on normal shutdown
- Still exits 0 even if flush throws (swallow — must exit regardless)
- Guards against double-invocation (idempotent — only one close/flush/exit)
- Works as a SIGTERM/SIGINT handler (called with no args)

Register in the server bootstrap (`index.ts`):
```typescript
const server = serve({ fetch: app.fetch, port, hostname });
const gracefulShutdown = createGracefulShutdown(server, {
  flushLlmUsageEvents: shutdownLlmUsageWriter,
  exit: (code) => process.exit(code),
});
process.on('SIGTERM', () => void gracefulShutdown());
process.on('SIGINT', () => void gracefulShutdown());
```

## Call-site telemetry integration pattern

When adding telemetry to a new LLM call site:

1. Import `enqueueLlmUsageEvent` from the **writer** module (`llm-telemetry-writer.js`), NOT the persistence module.
2. Import `REQ_ID_STORAGE, TRACE_ID_STORAGE` from the logger (for correlation IDs).
3. After a successful LLM call, enqueue with `outcome: 'success'` and token counts from `completion.usage`.
4. In the catch block, enqueue with `outcome: 'failed'` and zero tokens.
5. Wrap telemetry in try/catch — telemetry failure must NOT block the response.
6. Use `eventId: ${reqId}:${route}:${model}` and `eventId: ${reqId}:${route}:${model}:failed` (the `:failed` suffix prevents collision).
7. Sanitize model names with `.replace(/[^A-Za-z0-9._:-]/g, '_')` — OpenRouter model strings contain `/`.
8. If the `chatCompletion` is inside a loop (e.g., tool-call rounds), track `lastCompletion` outside the loop scope so telemetry can read it after the loop exits.

Useful Vitest details:

- If a mocked dependency uses a fixture referenced by a hoisted `vi.mock`, create it with `vi.hoisted(() => ({ ... }))`.
- Migration definitions may expose SQL as an array; execute each statement independently in isolated migration tests.
- Verify redaction by serializing the resulting event and asserting prompts, completions, credentials, and arbitrary metadata are absent.