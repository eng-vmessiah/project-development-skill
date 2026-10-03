# Context — PD Fleet → Hermes Real Adapter v1

## Provenance

This is a new follow-up scope opened after `pd-fleet-hermes-adapter-v0` reached `passed_local_fake_only` / `NOT_READY_RUNTIME`. The previous fake-only scope intentionally stopped before Hermes/provider integration.

## Current architecture boundary

```text
PD Core
  → owns SPEC, PLAN, gates, evidence, and human delivery decisions
PD Fleet
  → owns task lifecycle, lease/fencing, bounded envelope, reports, cleanup
Real adapter (future)
  → translates the bounded Fleet envelope to a runtime contract
Hermes Runtime Host
  → owns sessions, delegate_task, providers, tools, credentials, policy/capabilities
Provider/sandbox
  → owns model execution and external effects, only if separately authorized
```

## Inherited v0 contract

The v0 contract remains the starting point for discovery:

```text
prepare → execute → observe → cancel → handoff → cleanup
```

The canonical lineage remains:

```text
Mission → MissionRun → Lane → Attempt → SessionHandle → WorkspaceDescriptor → Events/Artifacts
```

Native Hermes handles, prompts, credentials, PIDs, commands, environment, and absolute paths must not cross the public Fleet/API boundary.

## Design constraints

- Fleet state and Hermes session state remain distinct sources of truth.
- The adapter must not silently become a provider router, sandbox, credential broker, or deployment mechanism.
- Every external effect requires an explicit capability and an auditable scope/run binding.
- Cancellation and timeout must preserve the original terminal outcome and cleanup semantics already proven by v0.
- A real adapter must be testable with injected runtime/delegate interfaces before any live Hermes call is considered.
- Discovery must distinguish facts, decisions, hypotheses, risks, and open questions.

## Open questions — discovery only

1. Which Hermes-native interface is the supported integration seam: direct `delegate_task`, gateway/API, or another host-owned capability?
2. What stable request/response shape is available without leaking prompts, credentials, native handles, or absolute paths?
3. How are session ownership, cancellation, timeout, retry, and cleanup represented by Hermes?
4. Which capability/policy checks must happen in PD Fleet, in the adapter, and in Hermes?
5. How are provider readiness, provider selection, and provider failure classified without making the Fleet adapter own provider policy?
6. What persistence and replay guarantees exist across Fleet and Hermes restarts?
7. What human approval and canary boundaries are required before any external effect?

No answer should be invented by implementation. Unresolved answers remain `OPEN`/`HOLD`.
