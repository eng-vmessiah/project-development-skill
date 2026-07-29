# Gateway Fleet Bridge — Discovery Baseline

**Status:** `G0_pending`
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

## Not yet confirmed

The following remain G0 questions and must be verified before a bridge contract is declared ready:

1. whether standalone terminal sessions publish through the same Gateway;
2. whether the existing event channel is chat/PTY scoped or globally usable;
3. whether a supported Fleet subscription/registration API exists;
4. Gateway auth and local ownership semantics for a non-UI client;
5. replay/cursor guarantees after reconnect;
6. stable versus presentation-only event payload fields.

## Decision

Current decision: `HOLD_G0_PENDING`. The available Gateway evidence is promising and materially better aligned than ACP for the desired user-started-session flow, but it is not yet authorization to implement or activate a live bridge.
