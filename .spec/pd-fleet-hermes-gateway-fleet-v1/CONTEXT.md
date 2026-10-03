# Gateway Fleet Bridge — Context and Reconciliation

## Why this scope exists

The prior real-adapter scope compared direct internal `delegate_task`, ACP, and MCP. That comparison remains historical evidence, but it targeted the wrong first product question: it assumed Fleet needed to create and execute Hermes child tasks.

The product direction is instead that a user starts a Hermes session and Fleet becomes aware of it. The existing Hermes dashboard demonstrates a reusable lower-level relation: the dashboard is a client of the Hermes Gateway, using JSON-RPC/WebSocket and event streams. Fleet should reuse that relation without using the dashboard.

## Current facts from read-only inspection

- Hermes CLI exposes `dashboard`, `serve`, and `acp` surfaces.
- `dashboard` and `serve` share the Hermes Gateway backend; `serve` is the headless backend for desktop/remote clients.
- The web UI uses `/api/ws` for JSON-RPC/WebSocket communication and `/api/events?channel=...` as a passive event subscriber.
- The standalone TUI uses the same logical `tui_gateway.server.dispatch`, but by default starts `python -m tui_gateway.entry` and communicates over newline-delimited stdio. It only uses an external Gateway WebSocket when `HERMES_TUI_GATEWAY_URL` is set.
- The classic `hermes --cli` path does not use `tui_gateway`; it has its own session-id/context path.
- `session.create` returns a live `session_id` and a separate stored session key; the live ID is routed to the transport/session registry.
- Existing Gateway event names include `session.info`, `status.update`, tool lifecycle events, message lifecycle events, approval requests, background completion, and errors.
- `/api/events?channel=...` requires a valid channel, fans out only to subscribers of that in-memory channel, has no wildcard/global subscription, cursor, replay, acknowledgement, or durable event log.
- Gateway WebSocket access is authenticated/host-checked; the observed mechanisms include session token, single-use ticket, and process credential depending on mode. A Fleet-specific client authorization contract does not yet exist.
- Hermes persists conversation/session history separately, but the event stream itself is not persisted for replay.

Read-only evidence references:

```text
hermes-agent-routing/hermes_cli/main.py
hermes-agent-routing/ui-tui/src/entry.tsx
hermes-agent-routing/ui-tui/src/gatewayClient.ts
hermes-agent-routing/ui-tui/src/app/useSessionLifecycle.ts
hermes-agent-routing/cli.py
hermes-agent-routing/tui_gateway/entry.py
hermes-agent-routing/tui_gateway/server.py
hermes-agent-routing/tui_gateway/ws.py
hermes-agent-routing/tui_gateway/event_publisher.py
hermes-agent-routing/hermes_cli/subcommands/dashboard.py
hermes-agent-routing/hermes_cli/web_server.py
hermes-agent-routing/hermes_cli/dashboard_auth/routes.py
hermes-agent-routing/web/src/pages/ChatPage.tsx
hermes-agent-routing/web/src/components/ChatSidebar.tsx
hermes-agent-routing/tests/hermes_cli/test_web_server.py
```

## G0 conclusions

1. The dashboard and standalone TUI share the Gateway **dispatcher logic**, but not necessarily the same transport or server process.
2. A user who starts the default standalone TUI cannot currently be assumed to be visible to an external Fleet Gateway client: its local stdio Gateway is a child process unless an external Gateway URL is configured.
3. The current `/api/events?channel` relation is dashboard/PTY-chat scoped and best-effort. It is not a suitable global Fleet stream.
4. The existing Gateway is still the right architectural seam, but Fleet needs either a supported registration/subscription surface or a Hermes-owned Gateway extension for global/session-scoped events.
5. The classic CLI path is a separate integration question and must not be silently included in the TUI observer contract.

## Decision

`G0 = HOLD_GLOBAL_FLEET_SURFACE_UNCONFIRMED`.

The inventory is complete enough to reject the dashboard channel as the Fleet contract and to select the Gateway as the host seam. It is not enough to authorize implementation because no supported global Fleet subscription, registration method, replay contract, or Fleet-specific auth boundary was found.

The next design target is a Hermes-owned Gateway extension/bridge contract, initially read-only, rather than an ACP executor or direct database reader.