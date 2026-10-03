# Gateway Fleet Bridge — Discovery Baseline

**Status:** `G0_hold_global_fleet_surface_unconfirmed`
**Mode:** read-only reconciliation
**External effects:** disabled

## Initial evidence

The Hermes checkout contains a Web UI that is a client of a shared Hermes backend. The documented and observed surfaces include:

- `web/README.md`: dashboard UI, API proxy, active/recent session page, and shared backend;
- `hermes_cli/subcommands/dashboard.py`: `dashboard` and headless `serve` use the same Gateway backend;
- `apps/shared/src/json-rpc-gateway.ts`: typed JSON-RPC/WebSocket client and Gateway event envelope;
- `web/src/components/ChatSidebar.tsx`: passive `/api/events?channel=...` subscription plus `/api/ws` client;
- `tui_gateway/server.py`: Gateway session methods including `session.create` and session metadata/state handling.

## Confirmed architectural interpretation

The dashboard is not the integration target. It is evidence that Hermes already has a client-facing Gateway/event relationship that a Fleet bridge may reuse. Fleet should be a sibling Gateway client or a Hermes-owned Gateway hook, with no dependency on dashboard UI code.

## G0 findings

The standalone TUI and dashboard share the logical `tui_gateway.server.dispatch`, but the default standalone TUI uses a local stdio child Gateway. The dashboard/serve WebSocket is therefore not automatically a view of every terminal session.

The dashboard event endpoint is not a Fleet stream:

- it requires an opaque `channel` tied to a PTY/chat surface;
- it fans out only to current subscribers of that in-memory channel;
- it has no global wildcard, cursor, replay, acknowledgement, or durable event log;
- it is best-effort and protected by dashboard/WebSocket auth mechanisms;
- its publisher path has bounded in-memory buffering and can drop frames.

The classic `hermes --cli` path is separate from `tui_gateway` and needs a separate integration decision.

## Decision

`G0 = HOLD_GLOBAL_FLEET_SURFACE_UNCONFIRMED`.

The Gateway remains the correct host seam, but implementation is blocked until a supported Hermes-owned Fleet registration/subscription surface is designed and authorized. Reusing `/api/events?channel` as a global Fleet contract is rejected.

## G1 product decision

Fleet is an external Gateway client activated from a user-started Hermes session after an explicit PD goal or Fleet coordination request. The Fleet bridge must receive a bounded activation/association signal; it must not parse arbitrary prompt text or automatically observe/control every user session.

The activation signal and the event stream are separate concerns. Activation identifies the intended session and bounded PD association. The initial stream contains only lifecycle/operational metadata: `session.registered`, `session.status_changed`, `session.heartbeat`, `session.metadata_changed`, `session.detached`, and `session.ended`.

The initial association remains `user_owned_session` and read-only. `fleet_owned_task` is a later, separately authorized mode requiring explicit ownership, capability, lease, and policy checks. Raw prompt content, history, tool output, provider responses, credentials, and terminal frames are excluded from the v1 contract.

## Remaining questions moved to G1/G2/G3/G4

- G1: stable versioned Fleet event envelope and supported Gateway extension;
- G2: user-owned versus Fleet-owned session association;
- G3: cursor, replay, reconnect, and stale-session behavior;
- G4: Fleet client authentication, authorization, redaction, and capability boundary.
