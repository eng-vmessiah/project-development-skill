# Hermes Fleet Observer Patches

## Local Hermes worktree

- Repository: `/home/vitor/.hermes/hermes-agent`
- Implementation worktree: `/home/vitor/project/hermes-agent-fleet-observer`
- Branch: `feat/fleet-observer-seam`
- Base: `3bb422a10f`
- Observer commit: `7e27e622e4`
- Transport foundation commit: `b676501577`

## Replayable patches

### 0001 — observer contract

```text
0001-fleet-observer-contract.patch
SHA-256: 89f0a144596a363d489ff48ee2af6a643a0798005877fef770dff04864253575
```

### 0002 — disabled attachment transport foundation

```text
0002-disabled-attachment-transport.patch
SHA-256: dfb6768c146772a9df8c203b1e81eba960dbe90eda7353221c0c84f6cd850d75
```

### 0003 — API-server gated transport composition

```text
0003-api-server-gated-transport.patch
SHA-256: 2e71c96849120a2b7a934e81e9f11c2a2b8ad51e239bb3fb2c3871ea952f682c
```

### 0004 — typed activation owner and lifecycle publisher

```text
0004-typed-activation-owner-lifecycle-publisher.patch
SHA-256: 49bf8dc982a9aee4e9c16a1986342ce574729b510edaf935ba0bc19ab8ab2ff8
```

### 0005 — fail-closed auth and lifecycle seam

```text
0005-fail-closed-auth-lifecycle-seam.patch
SHA-256: 0c0769c1870aebc88e48e44e66edb827df1b8c49bf1f19fe71b43c057b29cd8f
```

### 0006 — verified dashboard Session identity adapter

```text
0006-dashboard-session-identity-adapter.patch
SHA-256: 0156bec9c9932889500f084de93d35713fa16250c4d22a9035b0b63faabdebd7
```

### 0007 — session request/lifecycle bridge

```text
0007-session-request-lifecycle-bridge.patch
SHA-256: d266c4eed9009fdce6bb927ba9b7c1efed694433f2b7bddb1e80b723ef2d94f8
```

### 0008 — bounded per-session activation tickets

```text
0008-bounded-session-activation-tickets.patch
SHA-256: 4327004411dc7ec89479c427ca98ca5d9e49240074c920f7046c1e835f8b0527
```

### 0009 — ticket attach and session lifecycle

```text
0009-ticket-attach-session-lifecycle.patch
SHA-256: 0ce5801e1014caaddd54419a70aff6c43279f7f8801f79671ce7b7654db6749a
```

Apply in order to a clean Hermes checkout based on the same base:

```bash
git am .spec/pd-fleet-hermes-gateway-fleet-v1/patches/0001-fleet-observer-contract.patch
git am .spec/pd-fleet-hermes-gateway-fleet-v1/patches/0002-disabled-attachment-transport.patch
git am .spec/pd-fleet-hermes-gateway-fleet-v1/patches/0003-api-server-gated-transport.patch
git am .spec/pd-fleet-hermes-gateway-fleet-v1/patches/0004-typed-activation-owner-lifecycle-publisher.patch
git am .spec/pd-fleet-hermes-gateway-fleet-v1/patches/0005-fail-closed-auth-lifecycle-seam.patch
git am .spec/pd-fleet-hermes-gateway-fleet-v1/patches/0006-dashboard-session-identity-adapter.patch
git am .spec/pd-fleet-hermes-gateway-fleet-v1/patches/0007-session-request-lifecycle-bridge.patch
git am .spec/pd-fleet-hermes-gateway-fleet-v1/patches/0008-bounded-session-activation-tickets.patch
git am .spec/pd-fleet-hermes-gateway-fleet-v1/patches/0009-ticket-attach-session-lifecycle.patch
pytest -q tests/hermes_cli/test_fleet_observer.py tests/hermes_cli/test_fleet_observer_transport.py tests/hermes_cli/test_fleet_activation.py tests/hermes_cli/test_fleet_session_bridge.py tests/gateway/test_api_server_fleet_observer.py
```

## Evidence

- Observer + transport focused suite: **63 passed**
- B8 API-server composition + SSE/body-boundary tests: **74 passed**
- B9 typed activation/principal foundation: **84 passed**
- B10 auth/lifecycle fail-closed seam: **284 passed**
- B11 verified dashboard Session adapter: **293 passed**
- B12 session request/lifecycle bridge: **308 passed**
- B13 bounded per-session activation tickets: **312 passed**
- B14 ticket attach/session lifecycle integration: **316 passed**
- API-server/observer focused regression gate: **288 passed**
- Full repository regression: **1198 passed**
- Python compilation: passed
- `git diff --check`: clean
- No active runtime restart or live route enablement

## Scope of approved patches

The patches add:

- disabled-by-default in-process observer contract/hub;
- bounded opaque ticket issuer;
- internal issuance capability;
- server-side attachment records;
- principal/association-bound consume and access;
- bounded injected HTTP/SSE contract;
- cursor/gap/TTL/overflow handling;
- redacted metadata-only event serialization;
- explicit `NOT_READY` status until wiring/auth capabilities exist;
- API-server route composition behind exact-boolean `pd_fleet_gateway_enabled`;
- aiohttp SSE bridge with bounded request bodies and cancellation cleanup;
- typed owner-issued `FleetPrincipal` with exact `pd:observe` capability;
- activation epoch and owner-bound binding validation;
- bounded lifecycle publisher for allowlisted session metadata;
- fail-closed typed principal resolver at the API-server boundary;
- lifecycle hook that refuses raw API-key/request claims;
- verified dashboard `Session` → Fleet identity adapter for user-owned sessions;
- explicit rejection of dashboard `TokenPrincipal` as human user identity;
- cookie-only dashboard Session request bridge with provider delegation;
- all API agent paths pass request context to the bridge;
- disabled flag blocks identity resolution and lifecycle publication;
- bounded per-session activation registry;
- monotonic TTL, opaque one-shot ticket, hashed storage;
- consume/revoke/expiry/epoch invalidation;
- per-session binding scope without public activation endpoint;
- explicit ticket-to-attach lifecycle integration;
- authoritative API session create/status/end hooks when an integration is injected;
- forged-principal teardown protection;
- cleanup/revoke on lifecycle publication failure.

They do not modify:

- `gateway/run.py`;
- dashboard routes or `/api/events`;
- dashboard authentication or existing tickets;
- `state.db` or other persistence;
- credentials/providers/tools/dispatch/session mutation;
- gateway startup or runtime process behavior.

## Remaining live blocker

The B14 seam now connects ticket consumption to an injected session lifecycle integration and API create/status/end hooks. It is still not exposed through a public activation endpoint or wired into live Hermes transport. Live Fleet still requires:

- a trusted internal activation caller and authorization gate;
- real transport attach/subscription consumption;
- durable/session-authoritative association and replay;
- controlled feature-flag rollout;
- smoke tests against the real API server;
- rollback and controlled restart authorization.

Do not apply the patches to the active runtime automatically. The running gateway uses `/home/vitor/project/isis/bridge/.venv`, not this worktree.
