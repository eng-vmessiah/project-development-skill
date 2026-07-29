# Gateway Fleet Bridge — Context and Reconciliation

## Why this scope exists

The prior real-adapter scope compared direct internal `delegate_task`, ACP, and MCP. That comparison remains historical evidence, but it targeted the wrong first product question: it assumed Fleet needed to create and execute Hermes child tasks.

The product direction is instead that a user starts a Hermes session and Fleet becomes aware of it. The existing Hermes dashboard demonstrates a reusable lower-level relation: the dashboard is a client of the Hermes Gateway, using JSON-RPC/WebSocket and event streams. Fleet should reuse that relation without using the dashboard.

## Current facts from read-only inspection

- Hermes CLI exposes `dashboard`, `serve`, and `acp` surfaces.
- `dashboard` and `serve` share the Hermes Gateway backend; `serve` is the headless backend for desktop/remote clients.
- The web UI uses `/api/ws` for JSON-RPC/WebSocket communication.
- The web UI uses `/api/events?channel=...` as a passive event subscriber for its PTY/chat channel.
- Existing Gateway event names include `session.info`, `status.update`, tool lifecycle events, message lifecycle events, approval requests, background completion, and errors.
- Hermes Gateway has session methods such as `session.create` and persists session metadata internally.

These facts do not yet prove that every standalone terminal session is attached to the same Gateway, nor that the dashboard channel is a suitable global Fleet event stream. G0 must verify that distinction.

## Design hypothesis

A `FleetGatewayBridge` should be a separate Hermes/Fleet client boundary first. It should consume a supported Gateway event/command surface and translate only bounded, versioned events into Fleet state. If the Gateway lacks a durable/global subscription suitable for Fleet, a small Hermes-owned Gateway hook/channel may be proposed in a later implementation scope.

## Non-goals and safety

This scope does not install dependencies, start Hermes, contact providers, access credentials, modify configuration, dispatch tasks, or read/write live runtime state. All runtime behavior must first be represented by injected Gateway doubles and local fixtures.

## Open questions

1. Does a standalone interactive `hermes` session publish through the same Gateway used by the dashboard?
2. Is `/api/events?channel=...` scoped to a PTY/chat channel, and is there a supported global/session event subscription for Fleet?
3. What supported local authentication/authorization should a Fleet client use?
4. Which Gateway event payload fields are stable and safe to persist?
5. What cursor/replay guarantees exist after reconnect?
6. Can Fleet register metadata without claiming ownership of a user-owned session?
7. Which controls, if any, can be exposed for user-owned sessions after explicit consent?
