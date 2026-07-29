# PD Fleet → Hermes Gateway Fleet Bridge v1 — State

- **Status:** `g0_hold_global_fleet_surface_unconfirmed`
- **Plan:** `pd-fleet-hermes-gateway-fleet-v1`
- **Current gate:** `G0_hold_global_fleet_surface_unconfirmed`
- **Supersedes:** `pd-fleet-hermes-adapter-real-v1` as current direction
- **Parent:** `pd-fleet-hermes-adapter-v0` — `passed_local_fake_only` / `NOT_READY_RUNTIME`
- **Owner/orchestrator:** `isis`
- **Scope authorization:** discovery/design only
- **External effects:** disabled
- **Runtime/provider authorization:** none
- **Implementation authorization:** none

## Authority boundary

Hermes Gateway owns concrete session/runtime state. Fleet owns coordination state. PD Core owns intent, contracts, gates, and human delivery decisions. The dashboard is a sibling presentation client and is not a Fleet dependency.

## Operating modes

| Mode | Initial Fleet role | Control status |
|---|---|---|
| `user_owned_session` | discover, observe, heartbeat, attach metadata, detach | read-only/default-deny |
| `fleet_owned_task` | task lifecycle and explicit coordination | future, separately authorized |

## Gates

| Gate | Status | Purpose |
|---|---|---|
| G0 | `hold` | inventory complete; supported global Fleet surface is unconfirmed |
| G1 | `not_started` | define versioned Gateway → Fleet contract |
| G2 | `not_started` | define ownership and association |
| G3 | `not_started` | define cursor/replay/reconnect/stale semantics |
| G4 | `not_started` | define security/capability/effect boundaries |
| G5 | `not_started` | define injected tests and local observer harness |
| G6 | `not_authorized` | future read-only implementation |
| G7 | `not_authorized` | future isolated local canary |
| G8 | `not_started` | closeout and explicit promotion decision |

## G0 result

The Gateway is confirmed as the correct host seam, but the current dashboard channel cannot serve as the Fleet contract. The default standalone TUI uses a local stdio Gateway child; the classic CLI is separate; no supported global Fleet subscription, registration method, replay contract, or Fleet-specific auth boundary was found.

G0 therefore remains a technical hold, not a failed discovery. G1 must design the smallest Hermes-owned Gateway extension/bridge needed for Fleet, initially read-only.

## Resume

Start with G1 contract design. Do not start Hermes, install dependencies, access credentials, change config, connect to a live Gateway, or implement runtime code from this scope.
