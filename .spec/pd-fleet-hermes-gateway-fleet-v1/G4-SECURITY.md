# G4 — Security, Capability, and Effect Boundaries

**Status:** `local_verified_live_open`
**Scope:** local/fake/injected implementation and verification; live Hermes seam excluded
**Implementation authorization:** local/fake/injected only; no live runtime/production
**External effects:** disabled

## 1. Security objective

Permit an authenticated Fleet observer to receive bounded, redacted lifecycle metadata for an explicitly activated `user_owned_session`, while making every runtime/control effect default-deny.

This is an observation authorization model, not a runtime authorization model.

## 2. Principals and trust boundaries

| Principal | Trust/authority | Required proof |
|---|---|---|
| Hermes Runtime/Gateway | authoritative issuer of session identity and activation provenance | Hermes-owned authenticated boundary |
| Fleet Gateway Bridge | translator and observer client | authenticated transport plus Fleet client identity |
| PD Fleet | authority for coordination records | own session/task authorization; not Hermes runtime authority |
| PD Core | authority for intent/acceptance/gates | own human/contract decision records |
| dashboard | sibling presentation client | never a Fleet trust anchor |

A caller-provided `session_ref`, `owner_ref`, `profile_ref`, `workspace_ref`, capability list, or activation object is untrusted input until validated by the supported Hermes-owned boundary.

## 3. Authentication and activation requirements

The eventual supported seam MUST provide:

1. authenticated transport identity for the Fleet observer;
2. an issuer-verifiable activation artifact from Hermes;
3. binding to `session_ref`, `owner_ref`, `profile_ref`, `workspace_ref`, and `ownership_mode`;
4. purpose restriction to `pd_observation` for v1;
5. `issued_at`/`expires_at` validation with bounded clock skew;
6. nonce or equivalent replay protection;
7. single-use or idempotent activation semantics;
8. revocation/expiry handling;
9. audit/provenance references without raw runtime content.

The design direction is an opaque, Gateway-resolved, short-lived one-use activation ticket. The concrete Hermes-owned transport authentication, ticket issuance/verification API, storage/consume implementation, rotation, and revocation mechanism remain open; no mechanism is assumed to exist today.

## 4. Capability matrix

| Capability | `user_owned_session` v1 | `fleet_owned_task` |
|---|---:|---:|
| register observer | allow | separate auth |
| attach explicit association | allow | separate auth |
| read redacted lifecycle metadata | allow | separate auth |
| replay approved bounded events | allow after G3 | separate auth |
| heartbeat/reconcile association | allow | separate auth |
| receive prompt/history | deny | deny by default |
| receive tool args/results | deny | deny by default |
| receive provider responses/credentials | deny | deny |
| dispatch or prompt injection | deny | separate future capability |
| cancel/mutate Hermes session | deny | separate future capability |
| activate provider/model | deny | deny by default |
| mutate filesystem/subprocess/network/external messaging | deny | deny by default |
| write Hermes `state.db` or runtime state | deny | deny |

No capability may be inferred from transport reachability, dashboard membership, session existence, or Fleet task state.

## 5. Redaction and bounded output

Redaction MUST happen before Fleet persistence, event translation, replay, or external delivery. The v1 output schema is closed and limited to the fields in `G1-CONTRACT.md`.

Reject by default:

- arbitrary maps or free-form metadata;
- prompts, conversation history, message text;
- tool arguments/results and approval payloads;
- provider/model response content;
- credentials, tokens, secrets, cookies;
- filesystem paths or terminal frames;
- unbounded arrays, strings, nested objects, or binary content.

Unknown fields, unknown enum values, oversized values, malformed provenance, and unsupported schema versions fail closed.

## 6. Error and audit requirements

Errors are stable bounded codes:

```text
unauthenticated
observer_not_authorized
activation_invalid
activation_expired
activation_replayed
activation_binding_mismatch
foreign_owner
association_required
association_stale
invalid_provenance
unsupported_schema
unsupported_event
invalid_event
payload_too_large
capability_denied
cursor_expired
cursor_stale
replay_gap
resync_required
no_new_events
```

Audit records may contain code, actor/reference IDs, association reference, timestamp, and outcome. They MUST NOT contain raw prompts, provider responses, credentials, tool payloads, or terminal content.

## 7. Effect boundary

The bridge may:

- validate an observer request;
- validate a Hermes-issued activation artifact;
- create/update/delete its own bounded observation association;
- persist redacted lifecycle metadata;
- emit bounded observer errors and reconciliation records.

The bridge may not:

- start or stop Hermes;
- dispatch prompts;
- execute tools;
- activate/change providers or models;
- cancel or mutate a user session;
- read/write Hermes internals or `state.db` directly;
- access credentials;
- open arbitrary network connections;
- send external messages;
- claim `fleet_owned_task` without separate authorization.

## 8. Open decisions for G4 closure

Each decision has an accountable role and required evidence:

| Decision | Accountable owner | Closure evidence |
|---|---|---|
| select Hermes-owned authentication mechanism | Hermes Gateway owner | supported-seam reference and threat-model review |
| issuer verification and key/token rotation | Hermes Gateway owner + security reviewer | verification/rotation design and negative tests |
| clock-skew, TTL, renewal, and replay policy | Bridge/Fleet owner + security reviewer | bounded timing rules and replay probes |
| revocation source and audit retention | PD Fleet owner + PD Core governance owner | retention/redaction policy and audit fixtures |
| enum values, numeric bounds, and payload byte limits | Bridge/Fleet owner | versioned schema and boundary tests |
| redaction rules and tests | Security reviewer | denylist/allowlist tests with sensitive fixtures |
| transport-to-Fleet capability mapping | Hermes Gateway owner + PD Fleet owner | capability matrix and foreign-owner denial tests |

No item is considered closed by prose alone; each requires the named role's evidence and an explicit review decision.
