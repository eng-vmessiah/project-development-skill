# PD Fleet → Hermes Real Adapter v1 — State

- **Status:** `superseded_by_gateway_observer_direction`
- **Plan:** `pd-fleet-hermes-adapter-real-v1`
- **Current gate:** `superseded_redirect_to_gateway_fleet_v1`
- **Parent:** `pd-fleet-hermes-adapter-v0` — `passed_local_fake_only` / `NOT_READY_RUNTIME`
- **Owner/orchestrator:** `isis`
- **Scope authorization:** discovery/design only
- **External effects:** disabled
- **Runtime/provider authorization:** none
- **Implementation authorization:** none

## Decision boundary

This historical scope may be read for evidence. It is closed for the current direction and may not call Hermes, providers, network, credentials, subprocesses, gateway, cron, production sandbox, or live external effects.

## Waves

| Wave | Status | Purpose |
|---|---|---|
| D0 Discovery | `superseded` | ACP/direct-internal discovery preserved as historical evidence |
| I1 Implementation | `not_authorized` | real adapter code only after explicit authorization |
| C1 Canary | `not_authorized` | controlled runtime/provider exercise only after separate approval |

## Resume

Do not resume this scope. Start from `.spec/pd-fleet-hermes-gateway-fleet-v1/` and its G0 gate. Runtime integration remains unauthorized.
