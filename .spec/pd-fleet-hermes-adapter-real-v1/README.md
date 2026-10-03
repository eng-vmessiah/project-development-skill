# PD Fleet → Hermes Real Adapter v1 — Historical Discovery Scope

**Status:** `superseded_by_gateway_observer_direction`
**Parent evidence:** `pd-fleet-hermes-adapter-v0` — `passed_local_fake_only` / `NOT_READY_RUNTIME`
**Scope authorization:** discovery/design only
**External effects:** disabled

## Purpose

Define the boundary and acceptance gates for a future real Hermes runtime adapter. This scope remains a historical record of the ACP/direct-internal discovery; it does not implement or activate the adapter. The current product direction is reconciled in `../pd-fleet-hermes-gateway-fleet-v1/` and uses the Hermes Gateway as the primary integration seam.

## Explicit non-goals for this scope

- no live `delegate_task` call;
- no provider/model activation;
- no credentials, network, cron, subprocess, gateway, or sandbox changes;
- no runtime integration code;
- no production worker or persistence changes;
- no merge, push, release, deploy, or restart;
- no claim of Hermes/provider/runtime readiness.

## Entry evidence

The fake-only v0 seam is complete locally. Its contract, lineage, lifecycle, replay, cleanup, redaction, no-dispatch boundary, independent fixture harness, vertical runner, and closure reviews passed. The v0 fake module remains the contract reference, not an implementation target for live dispatch.

## Historical exit condition

A reviewed design packet exists with:

1. actual Hermes integration seam and capability inventory;
2. explicit Fleet → Hermes → Fleet bridge contract;
3. effect, credential, provider, sandbox, timeout, cancellation, and cleanup boundaries;
4. deterministic injected test strategy with no live effects;
5. risk/finding matrix and unresolved questions;
6. a separate implementation authorization proposal.

Discovery exit was not implementation approval. This scope is now superseded, not approved for implementation, provider access, or live dispatch. Do not resume it without an explicit scope decision that reopens the ACP/direct-runtime question.

## Redirect

Read-only Hermes Gateway inventory, user-owned session observation, Fleet event translation, cursor/reconnect semantics, and the G0–G8 reconciliation now belong to:

```text
.spec/pd-fleet-hermes-gateway-fleet-v1/
```
