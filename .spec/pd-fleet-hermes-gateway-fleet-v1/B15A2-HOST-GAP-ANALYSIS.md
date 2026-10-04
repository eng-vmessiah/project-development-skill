# B15a.2 — Host Integration Gap Analysis (Phase 1)

**Status:** `in_progress_local_only`
**Author:** ISIS (B15a.2 execution session, 2026-10-04)
**Authorization:** D7 (`D7-B15A2-AUTHORIZATION-REQUEST.md`) — local/default-off/read-only; no runtime activation, installation, provider, network, credentials, dispatch, push, merge, release.
**References:** `B15-TUI-SEAM.md` (D1/D4 approved), `B15A-TUI-WIRE-CONTRACT.md` (D4), `G4-AUTH-LIFECYCLE.md`, `G4-SECURITY.md`, `B15A-EXECUTION-PLANS.md` §B15a.2.
**Verified base (2026-10-04):** rebased series A `feat/b15a-rpc-seam-v2` @ `e98c30490b` and series B `feat/fleet-observer-seam-v2` @ `d501af7a68` on `origin/main` `ea81748579`; canonical per-file gateway suite identical to base (31 files, no new failures); fleet suites 31+4 and 120 passed.

## 1. Goal

Implement the **host side** of the approved read-only TUI Fleet protocol: the four D4 operations (`fleet.session.activate/status/deactivate/replay`) served through the default-off `fleet.*` RPC seam, scoped to the single authoritative active TUI session, with bounded/redacted events, cursor/replay/gap/TTL semantics, and deterministic detach. Outcome cap: `LOCAL_SEAM_VERIFIED / LIVE_NOT_READY`.

## 2. Topology

```text
PD observer (Fleet Core, repo)                          Hermes (worktrees, default-off)
  TuiD1BatchRegistrarAdapter ──registers four names──▶  PluginRpcRegistry  (fleet.* seam)
  fleet_d1_registration_bridge (injected host callable)   ├─ fleet.session.activate
                                                          ├─ fleet.session.status
                                                          ├─ fleet.session.deactivate
                                                          └─ fleet.session.replay
  fleet_gateway_bridge  ◀────── bounded wire ────────   FleetTuiSessionService (host, NEW)
                                                          ├─ server-side caller/observer + active-session resolution
                                                          ├─ FleetActivationOwner + session activation registry (tickets)
                                                          ├─ FleetSessionLifecycleIntegration (attach/end/detach)
                                                          └─ FleetObserver hub (events / cursor / retention)
```

The TUI JSON-RPC stdio channel is the first Hermes caller (B15-TUI-SEAM). The raw activation ticket never crosses to the TypeScript client.

## 3. Inventory — what already exists

### Hermes — seam (branch `feat/b15a-rpc-seam-v2`)

- `tui_gateway/plugin_rpc.py` — `PluginRpcRegistry`, `register`/`register_batch` (fleet namespace only, explicit `enabled` gate, reserved-collision rejection, duplicate rejection, atomic batch publication). ✓
- `tui_gateway/server.py` — `_plugin_rpc_registry`, `register_plugin_rpc(_batch)`, `clear_plugin_rpcs_for_tests`; dispatch boundary in `tui_gateway/rpc_dispatch.py`; focused tests `tests/tui_gateway/test_plugin_rpc_seam.py`. ✓
- `plugins/pd-fleet-hermes/` — lifecycle-only package + closed `integration_contract` validated before import (`plugins_manifest.py`, all-or-nothing gate). ✓ (registers zero RPCs, by design)

### Hermes — observer / activation machinery (branch `feat/fleet-observer-seam-v2`)

- `hermes_cli/fleet_activation.py` — `FleetPrincipal`, `FleetActivationOwner` (epoch, ready, principal/binding validation), `FleetActivationBinding`, `FleetLifecyclePublisher`, `FleetPrincipalResolver`, `DashboardSessionFleetIdentityAdapter`. ✓
- `hermes_cli/fleet_session_activation.py` — one-shot per-session activation tickets (hash-only storage, consume/revoke/expiry/owner-epoch invalidation, bounded TTL ≤3600s). ✓
- `hermes_cli/fleet_session_lifecycle.py` — ticket `attach()`, `status_changed()`, `ended()`, `detach()`, `registered_if_attached()`, `active()` over the observer scope. ✓ (currently composed only into the api_server path)
- `hermes_cli/fleet_observer.py` — event contract (6 event types), cursors (`stream_ref`, `stream_epoch`, `sequence`, `scope_key`, TTL 3600s, expiry), retention ≤24h, replay limit ≤100, gap/error taxonomy. ✓
- `hermes_cli/fleet_observer_transport.py`, `fleet_observer_aiohttp.py` — disabled attachment transport + routes (api_server path). ✓
- `hermes_cli/fleet_session_bridge.py` — cookie-only verified dashboard session request bridge (api_server path). ✓

### PD / Fleet (repo `main`)

- `scripts/pd_fleet/tui_readonly_contract.py` — closed request/binding/lease registry (≤128 records, TTL ≤300s, monotonic clock, fail-closed resolve/revoke). ✓
- `scripts/pd_fleet/fleet_d1_registration_bridge.py` — the four approved `fleet.session.*` names registered into an **injected** host registry, batched, default-off, client-authority denial. ✓
- `scripts/pd_fleet/tui_d1_batch_registrar_adapter.py` — forwards one ordered batch to an injected host callable (no per-name fallback). ✓
- Local composition checkpoint `93c33e9` — in-memory D1-compatible registrar/dispatcher proves bounded JSON-RPC responses, default-off publication, request-id validation, normalized registrar failure (`LOCAL_SEAM_COMPOSED`, `LIVE_NOT_READY`). ✓

## 4. Gap map (B15a.2 ordered tasks)

| # | Task (plan) | State | Missing (this phase) |
|---|---|---|---|
| 1 | Resolve session server-side; client never supplies `session_ref`/owner/principal | **MISSING** | Host-side resolution of caller/observer identity (TUI process/stdio connection, profile, workspace) **and** the authoritative active session inside `tui_gateway`; deny on absence/ambiguity. |
| 2 | Explicit `activate/status/deactivate` (+`replay`) RPC, default-off | **PARTIAL** | The four concrete handlers + D4 wire semantics; registration path when the integration flag is on; per-method gating. |
| 3 | ≤1 association per session; cross-scope rejection | **PARTIAL** | Ticket registry exists; **MISSING**: TUI-side association registry (one active observer per session) and cross-scope rejection at the wire boundary. |
| 4 | Versioned, bounded, redacted events | **PARTIAL** | Event contract/redaction exist internally; **MISSING**: closed D4 wire codec (`pd-fleet-tui:v1` envelope/event/snapshot/errors) + mapping that never leaks internal shapes. |
| 5 | cursor/replay/reconnect/gap/TTL/stale without duplicate association | **PARTIAL** | Cursor/retention/replay structures exist; **MISSING**: wire `replay` handler over the TUI session stream, retention/tombstone semantics at the association boundary, reconnect-without-duplicate proof. |
| 6 | Detach on deactivate / session-end / TUI-exit / crash-restart | **PARTIAL** | Lifecycle service exists (api path); **MISSING**: TUI session hooks emitting events + deterministic detach on session-end/TUI-exit; epoch invalidation on restart. |
| — | Wire PD contracts to the real host callable | **MISSING** | Local integration harness binding `TuiD1BatchRegistrarAdapter` to the host registry; live link deferred by design. |
| — | Non-Fleet byte-for-byte compatibility | **PARTIAL** | Seam dispatch tests exist; add non-Fleet golden checks around the new handlers. |

## 5. Implementation slices (RED-first)

- **S0 — integration branch:** create `hermes-agent-b15a2-integration` (D7 child branch) merging `feat/b15a-rpc-seam-v2` + `feat/fleet-observer-seam-v2`; suites green (31 + 4 + 120 + canonical gateway == base).
- **S1 — D4 wire codec** (`hermes_cli/fleet_tui_wire.py`): closed schemas; unknown fields/enums deny; opaque bounded refs; bounds (payload ≤4 KiB, envelope ≤8 KiB, replay ≤100 events; depth/string/cardinality limits; reject control/bidi/binary/NaN); canonical error set; recursive redaction. Tests RED-first, including redaction escape attempts.
- **S2 — host service** (`hermes_cli/fleet_tui_session.py`): `FleetTuiSessionService` — `activate/status/deactivate/replay`; resolves observer + active session server-side; single association per session; composes `FleetActivationOwner` + session activation registry + lifecycle + observer hub; fail-closed on every unresolved fact.
- **S3 — seam registration** (`tui_gateway`): default-off registration of the four handlers via `register_plugin_rpc_batch`; disabled/absent/duplicate/collision behavior; handler exception isolation; non-Fleet golden tests.
- **S4 — session hooks:** feed TUI session lifecycle into observer events (`session.registered/status_changed/heartbeat/metadata_changed/detached/ended`); detach on session-end/TUI-exit; restart epoch invalidation.
- **S5 — integration harness:** bind the PD `TuiD1BatchRegistrarAdapter` to the host registry; negative fixtures (duplicate presentation, concurrent duplicate, wrong observer, expired, revoked, malformed, cross-scope, replay gap, no session-existence disclosure).
- **S6 — independent review + evidence packet** → closeout `LOCAL_SEAM_VERIFIED / LIVE_NOT_READY`.

## 6. Constants (candidates — require owner/security approval before becoming normative)

Activation TTL 300s · association idle TTL 90s · heartbeat 30s · cursor TTL 900s · reconnect grace 60s · payload 4 KiB · envelope 8 KiB · replay batch 100. Implemented as one adjustable constants block; local values must not be promoted as normative without approval.

## 7. Invariants (tested, non-negotiable)

- Client supplies only `schema_version` (and `cursor` for `replay`); identity/association/session are always server-resolved.
- No prompts, history, tools, provider material, credentials, cookies, URLs, paths, terminal frames, or identity values in any wire object — recursive redaction before buffer/log/persistence/replay.
- `sequence` strictly increasing and contiguous per `(association_ref, stream_epoch)`; repeated/out-of-order/discontinuous ⇒ `invalid_provenance` / `replay_gap`, never silent success.
- Flag off ⇒ non-Fleet behavior byte-for-byte; Fleet methods unregistered and unreachable.
- No runtime effects: no install, no live-path activation, no network/provider/credentials, no session mutation.

## 8. Evidence required at closeout

Named tests/fixtures per G4 §9 mapped to the wire: absent/disabled/enabled/invalid configuration; foreign owner; ambiguous identity; duplicate attach; invalid/expired/stale cursor; replay gap; crash/restart; redaction escape attempts; non-Fleet golden; compile/diff/doc gates. Result reported separately for contract-only, fake/injected, TUI-process, Hermes-seam and live-authorization buckets; `local_verified` never replaces `NOT_READY_HERMES_SEAM`.
