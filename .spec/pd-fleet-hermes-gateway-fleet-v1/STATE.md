# PD Fleet → Hermes Gateway Fleet Bridge v1 — State

- **Status:** `g8_local_closeout_not_promotable`
- **Plan:** `pd-fleet-hermes-gateway-fleet-v1`
- **Current gate:** `G8_local_closeout_not_promotable`
- **Parent:** `pd-fleet-hermes-adapter-v0` — `passed_local_fake_only` / `NOT_READY_RUNTIME`
- **Owner/orchestrator:** `isis`
- **Scope authorization:** local/fake/injected implementation and verification only
- **External effects:** disabled
- **Runtime/provider authorization:** none
- **Live Hermes status:** `NOT_READY_HERMES_SEAM`
- **Hermes implementation WIP:** `/home/vitor/.hermes/hermes-agent` on `main` at `f66d3d4b06`; local host-side seam commit, unpushed and not installed/activated

## Gate statuses

| Gate | Status | Evidence / limitation |
|---|---|---|
| G0 | `HOLD_live_surface_unconfirmed` | No supported global Fleet subscription, activation, replay, or opaque issuer seam confirmed. |
| G1 | `local_verified` | Versioned bridge contract and review packet. |
| G2 | `local_verified` | Ownership/association rules and local tests. |
| G3 | `local_verified` | Cursor, replay, reconnect, stale, and recovery behavior in local fixtures. |
| G4 | `local_verified_live_auth_open` | Local default-deny/redaction/auth policy verified; Hermes Gateway mechanism, issuer, transport, and security closure remain open. |
| G5 | `local_fake_verified` | 45/45 scenarios; 44 distinct negative scenarios; direct and module runs deterministic. |
| G6 | `local_injected_verified_live_not_ready` | Local bridge and adapter verified; unsupported live Fleet operations explicitly return `NOT_READY_HERMES_SEAM`. |
| G7 | `local_fake_canary_verified` | Isolated fake Gateway canary only; no live or provider effect. |
| G8 | `local_closeout_not_promotable` | Documentation/evidence closeout complete; no promotion, merge, release, or production readiness claim. |

## Authority boundary

Hermes owns concrete session/runtime state. Fleet owns coordination state. PD Core owns intent, contracts, gates, and human delivery decisions. The dashboard remains a sibling presentation client and is not a Fleet dependency or global observer source. The TUI backend is now the planned first Hermes caller for B15a, but it is not yet wired to Fleet and does not authorize global observation.

## Implemented local artifacts

- `scripts/pd_fleet/fake_gateway.py`
- `scripts/pd_fleet/fleet_gateway_bridge.py`
- `scripts/pd_fleet/gateway_bridge_contracts.py`
- `scripts/pd_fleet/hermes_existing_adapter.py`
- `scripts/pd_fleet/fixture_harness.py`
- `scripts/pd_fleet/run_g5_fixture_matrix.py`
- `scripts/pd_fleet/hermes_plugin_contract.py` — local/injected lifecycle-only loader; not Hermes runtime integration
- `tests/fleet/test_hermes_plugin_contract.py` — 10 focused contract tests, including private-context isolation, staged rollback, and opaque-target rejection
- corresponding `tests/fleet/test_*` coverage and the existing v0 fake-only contract
- Hermes patch artifact: `patches/0001-fleet-observer-contract.patch`
- Hermes worktree commit: `7e27e622e4` on `feat/fleet-observer-seam` (disabled in-process contract only)
- Hermes transport foundation commit: `b676501577` (disabled/unwired attachment HTTP/SSE foundation)
- Hermes API-server composition commit: `2dcde7be81` (flag-gated route/SSE bridge, still `NOT_READY` without activation/auth)
- Hermes B15a.0 local seam checkpoint: `ec55552a80`, `tui_gateway/plugin_rpc.py`, dispatcher registration/error boundary and focused tests; local-only, not activated
- Hermes B15a.2 host-side seam checkpoint: `f66d3d4b06`, lazy namespaced plugin RPC staging/publication with focused tests; unpushed, uninstalled, and not activated
- PD/Fleet B15a.2 local read-only contract checkpoint: `scripts/pd_fleet/tui_readonly_contract.py` and `tests/fleet/test_tui_readonly_contract.py`; request/binding/redacted response only; no Hermes transport registration
- PD/Fleet D1 registration bridge checkpoint: `1084efc`, `scripts/pd_fleet/fleet_d1_registration_bridge.py` and focused tests; all four approved RPC names are injectable/default-off/local-only, with closed requests, no client identity authority and no Hermes import/transport registration.
- B15a.3 local composition checkpoint: `93c33e9`; an in-memory D1-compatible registrar/dispatcher composes the four approved Fleet methods and proves bounded JSON-RPC responses, default-off publication, client-authority denial, request-id validation and normalized registrar failure. Status: `LOCAL_SEAM_COMPOSED`, `LIVE_NOT_READY`.
- PD/Fleet B15a.1 local plugin checkpoint: `824f000`, `plugins/pd-fleet-hermes/` lifecycle-only package and tests; independent review `PASS`; not installed or discovered by Hermes runtime
- Hermes B15a.4 packaging/discovery checkpoint: `058c3fa620`; optional closed `integration_contract` is validated by the real PluginManager before import, while PD Fleet is staged/tested standalone default-off with lifecycle hooks only. Invalid contracts are rejected before import; no installation or runtime activation occurred. Status: `LOCAL_PLUGIN_DISCOVERY_VERIFIED`, `LIVE_NOT_READY`.
- B15a.5 runtime readiness packet: `B15A5-RUNTIME-READINESS-PACKET.md`, independently reviewed `APPROVED`; documentation-only and explicitly does not authorize installation, runtime discovery/activation or canary. Status: `PLANNED_READ_ONLY`, `LIVE_NOT_READY`.
- Replayable Hermes host patch: `patches/0010-hermes-lazy-namespaced-tui-rpc-seam.patch`
- Hermes B9 authority commit: `d3b761a99b` (typed principal, owner epoch, binding validation, lifecycle publisher)
- Hermes B10 fail-closed seam commit: `41c17d9bc0` (typed resolver and lifecycle hook; global API key is not Fleet identity)
- Hermes B11 identity adapter commit: `92f068bbff` (verified dashboard Session → FleetPrincipal; TokenPrincipal rejected as human identity)
- Hermes B12 request bridge commit: `d25ab5f4cc` (cookie-only verified Session bridge, provider delegation, all API agent paths carry request context, exact flag guard)
- Hermes B13 activation registry commit: `c4ed90d144` (bounded per-session binding, monotonic opaque one-shot tickets, hash-only storage, consume/revoke/expiry/epoch invalidation)
- Hermes B14 lifecycle integration commit: `25880126f4` (ticket-to-attach service, session-scoped registered/status/end/detach, API create/status/end hook composition, forged-principal teardown protection)
- Replayable patches: `patches/0001-fleet-observer-contract.patch`, `patches/0002-disabled-attachment-transport.patch`, `patches/0003-api-server-gated-transport.patch`, `patches/0004-typed-activation-owner-lifecycle-publisher.patch`, `patches/0005-fail-closed-auth-lifecycle-seam.patch`, `patches/0006-dashboard-session-identity-adapter.patch`, `patches/0007-session-request-lifecycle-bridge.patch`, `patches/0008-bounded-session-activation-tickets.patch`, `patches/0009-ticket-attach-session-lifecycle.patch`

## Next blocker

The next blocker is **B15a.2 host integration of the read-only PD Fleet RPC**. The local/injected request, host-binding, bounded capability, and redacted response contract is now covered by `scripts/pd_fleet/tui_readonly_contract.py`, but it does not implement Hermes authentication, owner/profile/workspace/observer/association binding, session resolution, transport registration, or live behavior. B15a.2 remains local-seam-only until Hermes owner/security review approves those boundaries. Live readiness remains `NOT_READY_HERMES_SEAM`.

After B15a, B15b must separately solve the messaging/API Gateway seam: authenticated registration, global or multi-session subscription, opaque ticket issuance/consume/revoke and issuer verification, durable cursor/replay/association semantics, and operational rollback. Until those waves are implemented, reviewed, and separately authorized, do not start live activation, access credentials, connect to a live Gateway, or treat the local fake as a runtime fallback.
