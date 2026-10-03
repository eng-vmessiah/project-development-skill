# D0.1 Discovery — Hermes Integration Surfaces

**Scope:** `pd-fleet-hermes-adapter-real-v1`
**Decision:** `D0.1_completed` / `D0.2_pending`
**Mode:** read-only repository inventory
**External effects:** disabled

## Findings

### F1 — Existing declarative runtime envelope

**Source:** `scripts/pd_fleet/runtime_adapter.py`

The repository already has a pure data-oriented `RuntimeTaskEnvelope`, `RuntimeResult`, `RuntimeAdapter` protocol, capability validation, bounded paths, redaction, timeout policy, and an injected `SandboxRunner` protocol. The module explicitly avoids process, network, environment, and config access.

**Implication:** this is a compatibility boundary and likely translation target, not proof of a Hermes-native integration. It cannot discover or invoke Hermes by itself.

### F2 — Existing named adapters are CLI-template adapters

**Source:** `scripts/pd_fleet/runtime_adapters.py`

Named adapters currently build argv templates for `hermes`, `codex`, `opencode`, and `claude`. Execution is delegated to an explicitly injected runner. Output parsing is bounded and fail-closed.

**Implication:** the existing `HermesRuntimeAdapter` name represents a command-template adapter, not a direct `delegate_task` bridge. Reusing it for a real Hermes host integration without a new contract would conflate CLI execution, host runtime sessions, and provider policy.

### F3 — Provider routing and dispatch are caller-injected

**Sources:** `scripts/pd_fleet/provider_routing.py`, `scripts/pd_fleet/provider_dispatch.py`

Routing consumes a caller-owned profile catalog and readiness declarations. Dispatch consumes caller-owned adapters and runners. It does not discover providers, credentials, environment, or network, and it records bounded audit events.

**Implication:** these modules provide reusable policy/evidence boundaries but do not establish the correct Hermes integration seam or authorize external execution.

### F4 — No repository-owned direct Hermes `delegate_task` bridge found

Repository search found references to `delegate_task` in documentation/skills, but no production module that invokes a native Hermes API or owns a direct session bridge.

**Implication:** the real integration seam cannot be inferred from the current repository. Hermes-side API/capability documentation and a supported host integration mechanism are required before D0.2 can be finalized.

### F5 — Provider readiness is explicitly read-only

**Source:** `docs/PROVIDER_READINESS.md`

Readiness probes may inspect provider authentication signals but must not auto-login, submit prompts, or make model calls. Runtime execution has separate capability and runner boundaries.

**Implication:** provider readiness must remain a separate prerequisite/evidence input, not be embedded in a Fleet adapter constructor or silently triggered by dispatch.

## F6 — Local Hermes CLI surfaces are host-level, not yet a Fleet bridge

**Evidence:** read-only `hermes --version`, `hermes --help`, `hermes acp --help`, `hermes mcp --help`, `hermes acp --check`, and `hermes mcp list`.

The installed Hermes is `v0.18.2` with CLI surfaces for ACP, MCP, proxy, gateway, and other host operations. `hermes acp --check` reports that ACP dependencies are not installed. MCP is configured for local servers, but MCP exposure is a tool/server boundary, not evidence of a supported Fleet-to-Hermes task-session bridge.

**Implication:** candidate integration surfaces now include an explicitly investigated ACP/MCP/proxy family, but none is selected. Installing ACP dependencies, changing MCP configuration, starting a proxy, or invoking a gateway is outside this discovery authorization.

## Current boundary map

```text
Fleet v0 contract
  → existing RuntimeTaskEnvelope / RuntimeResult compatibility boundary
  → [UNRESOLVED: supported Hermes host integration seam]
  → Hermes Runtime Host session/delegate capability
  → provider/sandbox only under separate authorization
```

## Facts vs. decisions vs. open questions

### Facts

- v0 fake-only contract and lifecycle are locally verified.
- Existing runtime adapters are injected CLI/sandbox adapters.
- Existing provider routing/dispatch are data/injection boundaries.
- No direct repository-owned native Hermes delegate bridge exists.
- Provider readiness probes are read-only.

### Decisions already established

- Fleet does not own Hermes session state, provider credentials, sandbox policy, or live effects.
- The real adapter must be a new, narrow bridge rather than silently repurposing the fake adapter.
- Discovery and tests must remain external-effect-free.

### Open / blocking questions

1. What supported Hermes host/API seam is available for a real adapter?
2. Is direct `delegate_task` invocation possible from the intended host process, or must the bridge use a gateway/IPC/API capability?
3. Which session identity, cancellation, timeout, handoff, and cleanup receipts are exposed by Hermes?
4. How are capability authorization and current PD run/scope binding passed into Hermes?
5. What provider readiness evidence is required and how is its freshness enforced?
6. What restart/replay semantics exist across Fleet and Hermes?

## D0.1 conclusion

`D0.1_completed`: repository seams are inventoried, and the key uncertainty is now explicit: the supported Hermes-native integration surface is not present in this repository and must be established from Hermes host documentation/configuration before designing the bridge contract.

No implementation authorization is implied.
