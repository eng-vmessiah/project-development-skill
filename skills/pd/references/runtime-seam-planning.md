# Runtime Seam Planning for Local-First Fleet Integrations

Use this reference when PD integrates with an existing runtime that has multiple entrypoints (messaging Gateway, dashboard, CLI, TUI backend, or worker).

## Core rule

Do not treat entrypoints as interchangeable. Inventory each caller, transport, session authority, lifecycle surface, and failure boundary. Select the narrowest trusted caller for the first implementation slice: prefer a local, user-triggered, server-side session boundary over a new public network endpoint.

## Recommended wave order

1. **Local seam:** one authoritative session, backend-owned identity, bounded/redacted events, default-off flag.
2. **Recovery seam:** attach/detach, cursor/replay, reconnect, TTL, crash/restart invalidation, and cleanup.
3. **Broader runtime seam:** only after the local slice is verified, address multi-session/global subscriptions and messaging/API callers as a separate wave.

## TUI-specific pattern

For a TUI backed by a local JSON-RPC/stdio child process:

```text
TUI client ↔ local gateway backend ↔ authoritative session ↔ Fleet observer
```

Activation and principal resolution stay in the backend. Do not send opaque activation tickets or security claims through the UI client. Start with the active session; do not infer global observation from a dashboard/WebSocket channel or from shared module names.

## Evidence and gates

- Fake/injected adapters prove contracts, not live transport wiring.
- Keep readiness `NOT_READY` until the actual runtime path is exercised.
- Test attach, duplicate attach, event delivery, replay cursor, reconnect, detach, session end, crash/restart invalidation, and flag-off compatibility.
- Document authority boundaries, non-goals, rollout gate, rollback, and the separate plan for messaging/API integration.
- A local TUI seam does not solve a messaging Gateway seam; keep those decisions and security reviews separate.

## Operational caution

Local TUI stacks may include Node/Ink, Python backends, and helper subprocesses. Include process/memory observation in canary validation, but do not infer causality from a single resource incident without fresh evidence.
