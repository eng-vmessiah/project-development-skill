# G8 Local Closeout

**Decision:** `local_closeout_not_promotable`

## Implemented and verified

- Local Fleet-side read-only bridge, contracts, fake Gateway, fixture harness, and existing-surface adapter are present in `scripts/pd_fleet/`.
- G5 fake/injected matrix: 45/45 scenarios passed, with 44 distinct negative scenarios; direct and module execution are deterministic.
- G6 local injected bridge/adapter behavior is verified, including fail-closed `NOT_READY_HERMES_SEAM` results for unsupported live operations.
- G7 isolated fake canary is verified with no live effects.
- Full suite evidence after attach hardening: 1198 passing.
- Documentation checker: 0 violations. `git diff --check`: clean.

## Hermes blocker work performed

A disabled-by-default Hermes-side in-process observer contract was implemented in an isolated worktree and reviewed locally:

- Worktree: `/home/vitor/project/hermes-agent-fleet-observer`
- Branch: `feat/fleet-observer-seam`
- Commit: `7e27e622e4`
- Evidence: 48 focused observer tests passed
- Replayable artifact: `patches/0001-fleet-observer-contract.patch`

A second disabled/unwired transport foundation was then implemented and approved locally:

- Hermes commit: `b676501577`
- Evidence: observer + transport focused suite: 63 passed
- Replayable artifact: `patches/0002-disabled-attachment-transport.patch`
- Server-side attachment, principal-bound consume, bounded HTTP/SSE contract, cursor/TTL/gap/overflow handling

This second slice still does **not** wire the real API server, resolve real authenticated principals, activate global subscription, or enable live Gateway access. It reduces the blocker to the Hermes API-server integration/activation gate but does not close G0/G4/G6 live.

A third B8 slice then added API-server composition behind an exact-boolean, default-off flag:

- Hermes commit: `2dcde7be81`
- Replayable artifact: `patches/0003-api-server-gated-transport.patch`
- API-server route registration only when `pd_fleet_gateway_enabled is True`
- aiohttp request/body bridge with bounded reads
- cancellable SSE loop and guaranteed cleanup
- flag-on but incomplete wiring remains `NOT_READY`
- Evidence: 288 focused API/observer tests; full repository regression 1198 passed

This B8 slice is locally verified but still does **not** provide a real Fleet principal/capability, activation owner, runtime event publisher, or live route enablement. It does not close G0/G4/G6 live.

A fourth B9 slice then added typed activation authority without enabling production:

- Hermes commit: `d3b761a99b`
- Replayable artifact: `patches/0004-typed-activation-owner-lifecycle-publisher.patch`
- owner-issued immutable `FleetPrincipal`
- exact `pd:observe` capability
- activation epoch and stale-artifact invalidation
- strict owner/observer binding validation
- allowlisted lifecycle metadata publisher
- Evidence: 84 focused observer/transport/API tests passed

This B9 slice is locally verified but is not yet connected to the real API authentication context or authoritative session lifecycle hooks. Live Hermes readiness remains `NOT_READY_HERMES_SEAM`.

A fifth B10 slice added a fail-closed boundary for real auth/lifecycle integration:

- Hermes commit: `41c17d9bc0`
- Replayable artifact: `patches/0005-fail-closed-auth-lifecycle-seam.patch`
- global API key remains ordinary API authentication and is never converted into Fleet identity
- typed resolver accepts only owner-issued principals
- lifecycle hook rejects raw request claims and publishes only typed, allowlisted metadata
- Evidence: 284 relevant API/observer tests passed

This B10 slice is locally verified but does not provide a real user/session principal provider or invoke publisher hooks from authoritative runtime lifecycle. Live readiness remains `NOT_READY_HERMES_SEAM`.

A sixth B11 slice added a verified dashboard identity adapter:

- Hermes commit: `92f068bbff`
- Replayable artifact: `patches/0006-dashboard-session-identity-adapter.patch`
- verified dashboard `Session` maps to owner-issued `FleetPrincipal`
- owner must match `session.user_id`
- expired/malformed sessions reject
- access/refresh tokens are never copied or logged
- `TokenPrincipal` remains service-to-service and is rejected as human identity
- Evidence: 293 relevant API/observer tests passed

This B11 slice is locally verified but is not connected to the API-server request/session bridge or authoritative lifecycle hooks. Live readiness remains `NOT_READY_HERMES_SEAM`.

A seventh B12 slice connected the verified Session bridge to API request paths without enabling Fleet:

- Hermes commit: `d25ab5f4cc`
- Replayable artifact: `patches/0007-session-request-lifecycle-bridge.patch`
- cookie-only access-token extraction with provider delegation
- exact API activation-owner/bridge provenance
- all chat/responses/runs paths pass request context
- no legacy raw-context resolver fallback
- exact disabled flag blocks identity and lifecycle publication
- Evidence: 308 relevant API/observer tests passed

The B14 seam is locally verified, but real Hermes transport attach/subscription and a trusted activation caller are still absent. The next planned caller is the local TUI backend (`tui_gateway.entry` / `tui_gateway.server`) through its JSON-RPC/stdio path, initially limited to the active session; the messaging/API Gateway remains a separate follow-up. Live readiness remains `NOT_READY_HERMES_SEAM`.

B14 provides an explicit, disabled-by-default integration boundary: owner-validated ticket consumption, session-scoped lifecycle publisher, and API create/status/end hook composition. It does not expose an activation endpoint, enable the hub, or connect the active Gateway.


The existing Hermes read-only adapter is not a Fleet observer. Hermes still lacks a verified, owner/security-reviewed mechanism for user-triggered activation, authenticated registration, global subscription, opaque ticket issuer/consume/revoke, issuer verification, durable association/replay, and operational rollback. Dashboard channel behavior is not substituted for that seam.

## Promotion decision

G8 is closed for local evidence and documentation reconciliation only. This is **not** production-ready, not merge/release approval, and not live Hermes readiness. No provider activation, live dispatch, credentials, session mutation, or Gateway activation is authorized. The live result remains `NOT_READY_HERMES_SEAM` / `HOLD_UNRESOLVED`.
