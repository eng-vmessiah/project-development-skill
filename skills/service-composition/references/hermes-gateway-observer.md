# Hermes Gateway Observer — reusable integration note

Use this reference when a project wants Fleet awareness of user-started Hermes sessions rather than Fleet-owned execution.

## Architecture finding

The Hermes dashboard is a client of a shared Hermes backend, not merely a static UI. The checked-out Hermes implementation exposes a JSON-RPC/WebSocket gateway (including `/api/ws`) and a passive event stream (`/api/events?channel=...`). Existing typed event names include `gateway.ready`, `session.info`, `message.start`, `message.delta`, `message.complete`, `thinking.delta`, `reasoning.delta`, `status.update`, `tool.start`, `tool.progress`, `tool.complete`, `clarify.request`, `approval.request`, `sudo.request`, `secret.request`, `background.complete`, and `error`.

Relevant implementation areas in the Hermes checkout:

- `apps/shared/src/json-rpc-gateway.ts` — JSON-RPC/WebSocket client types and event envelope;
- `web/src/components/ChatSidebar.tsx` — dashboard event subscription and session-info usage;
- `tui_gateway/server.py` — session methods such as `session.create`, session identity, profile/cwd/source, and runtime state;
- `hermes_cli/subcommands/dashboard.py` — `dashboard` and headless `serve` share the same backend server.

## Correct reuse pattern

For interactive sessions opened by the user:

```text
Hermes Gateway → Gateway Observer/Registry → Fleet projection/dashboard
```

Treat Fleet as a read-only or opt-in observer first. Reuse the gateway transport and event contract; do not create a new ACP executor or call `delegate_task` internals. ACP may remain a secondary transport for editor/session control, but it is not required for awareness when the gateway already carries session events.

## First slice

Implement or specify only:

- connect/authenticate;
- subscribe to session/event stream;
- register or discover session identity;
- project `session.info`, status, tool, message, approval, and error events;
- reconnect/resync/detach;
- explicit provenance (`gateway`, `session_id`, `profile`, `source`).

Default-deny these capabilities until separately authorized:

- prompt injection;
- cancellation or process termination;
- provider activation;
- credential access;
- filesystem/workspace control;
- external messaging.

## Critical boundary

The existing dashboard/gateway path does not automatically prove that every standalone `hermes` terminal process is attached to the same gateway. Confirm the actual launch topology. If standalone sessions are not gateway-backed, add an explicit registration/handshake, supported hook, wrapper, or relay; never rely on process-table guessing as the primary contract.

Do not read Hermes `state.db` directly as the primary integration. It is useful implementation evidence and possibly a later local fallback, but direct schema coupling is weaker than the gateway/API/event boundary.

## Mode split

- `interactive user-owned session`: Hermes owns runtime; Fleet observes and may offer explicitly authorized controls;
- `Fleet-dispatched task session`: Fleet owns task lifecycle; an adapter may use ACP or another supported host seam, while Fleet remains authoritative for task state.

These modes must not be collapsed into one lifecycle contract.