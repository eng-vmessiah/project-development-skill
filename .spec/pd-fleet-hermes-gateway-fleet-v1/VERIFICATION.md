# Gateway Fleet Bridge — Verification

**Status:** `g0_hold_global_fleet_surface_unconfirmed`
**Scope:** discovery/design only

This file will record G0–G8 evidence. No verification claim is made until the corresponding gate has fresh evidence.

## G0 evidence

**Result:** `HOLD_GLOBAL_FLEET_SURFACE_UNCONFIRMED`

Read-only source inspection confirmed:

- standalone TUI default path: local `tui_gateway.entry` over stdio;
- dashboard/serve path: shared Gateway backend with `/api/ws` WebSocket;
- shared logical dispatcher: `tui_gateway.server.dispatch`;
- `/api/events?channel` is an in-memory, channel-scoped, best-effort fan-out;
- no supported global subscription, cursor, replay, acknowledgement, durable event stream, or Fleet-specific auth/registration method was found;
- classic `hermes --cli` does not use `tui_gateway` and remains a separate integration path.

**Evidence references:**

```text
hermes-agent-routing/hermes_cli/main.py
hermes-agent-routing/ui-tui/src/gatewayClient.ts
hermes-agent-routing/ui-tui/src/app/useSessionLifecycle.ts
hermes-agent-routing/cli.py
hermes-agent-routing/tui_gateway/server.py
hermes-agent-routing/tui_gateway/ws.py
hermes-agent-routing/tui_gateway/event_publisher.py
hermes-agent-routing/hermes_cli/web_server.py
hermes-agent-routing/hermes_cli/dashboard_auth/routes.py
hermes-agent-routing/web/src/pages/ChatPage.tsx
hermes-agent-routing/web/src/components/ChatSidebar.tsx
hermes-agent-routing/tests/hermes_cli/test_web_server.py
```

**Interpretation:** G0 discovery is complete enough to reject the dashboard event channel as the Fleet contract and retain the Gateway as the host seam. It does not authorize implementation. The next gate must design a Hermes-owned Fleet registration/subscription extension.

## Current baseline

- Existing Hermes Gateway/dashboard source inspected read-only.
- Existing PD Fleet v0 fake-only contract preserved.
- No Hermes process, provider, network, credential, configuration, or live Gateway activated.
- No runtime implementation authorized.

## Required evidence before G8

- source/file references for Gateway surface and event semantics;
- user-owned versus Fleet-owned ownership matrix;
- versioned bridge/event contract;
- cursor/replay/reconnect tests;
- injected observer harness tests;
- capability and redaction review;
- documentation checker output;
- `git diff --check` output;
- independent spec/compliance and security/quality review;
- explicit human decision for any implementation or local canary.
