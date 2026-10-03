# G2 — Ownership and Session/Task Association

**Status:** `local_verified_live_open`
**Scope:** local/fake/injected implementation and verification; live Hermes seam excluded
**Implementation authorization:** local/fake/injected only; no live runtime/production
**External effects:** disabled

## 1. Authorities and lineage

```text
Hermes Runtime / Session
  → Hermes Gateway
  → Fleet Gateway Bridge
  → PD Fleet association record
  → PD Core goal/task lineage
```

| Object | Authority | Fleet relationship |
|---|---|---|
| Hermes session/runtime state | Hermes Runtime/Gateway | observed by bounded reference only |
| activation artifact | authenticated Hermes-owned boundary | evidence for an explicit association request; never caller-supplied proof |
| session association | PD Fleet | coordination record scoped to one session/owner/mode |
| Fleet task/run/lease/checkpoint | PD Fleet | operational coordination state |
| goal/SPEC/PLAN/DAG/gates | PD Core | intent and decision authority |

The Fleet association record MUST NOT masquerade as Hermes runtime state, user approval, provider state, or PD Core acceptance.

## 2. Ownership modes

| Mode | Owner | Initial Fleet capabilities | Control |
|---|---|---|---|
| `user_owned_session` | user/profile/workspace bound by Hermes-issued activation | observe lifecycle metadata, heartbeat, attach/detach metadata, replay through approved bridge | read-only/default-deny |
| `fleet_owned_task` | explicitly authorized Fleet task owner | future task lifecycle and coordination | not authorized in this scope |

No mode is inferred from session existence, prompt content, dashboard channel, or an arbitrary `owner_ref` supplied by the caller.

## 3. Association identity

An association is keyed by:

```text
(association_ref, session_ref, owner_ref, profile_ref, workspace_ref, ownership_mode)
```

The tuple is issued or attested by the Hermes-owned activation boundary and is opaque to Fleet except for equality/scoping. Fleet MUST preserve the original references and provenance; it MUST NOT replace them with locally invented ownership claims.

A duplicate request with the same valid `activation_ref` is idempotent and returns the existing association if all bound fields match. A request that reuses an activation reference with different session/owner/profile/workspace/mode returns external `activation_invalid`; `activation_binding_mismatch` is audit-only.

## 4. Attach and detach

### Attach

Attach succeeds only when:

1. the observer transport is authenticated;
2. the activation artifact is valid, unexpired, and issued by the supported Hermes boundary;
3. the artifact purpose is `pd_observation`;
4. the requested session/reference tuple matches the artifact;
5. the requested capability is allowed by the mode;
6. no foreign-owner or stale association conflict exists.

Attach creates or returns a Fleet association record. It does not start a provider, dispatch a prompt, mutate the Hermes session, or claim task ownership.

### Detach

Detach removes the Fleet observation relationship only. It MUST NOT close, cancel, interrupt, mutate, or delete the Hermes session. A detach event may be emitted by the Gateway as `gateway_native` or represented by Fleet reconciliation as a separate `fleet_reconciled` record. Fleet MUST NOT publish a reconciliation record as if it were a native Hermes event.

## 5. Duplicate, foreign, orphan, and stale behavior

| Condition | Required result |
|---|---|
| same valid association repeated | idempotent success; no duplicate association |
| same activation reused with changed binding | external `activation_invalid`; audit `activation_binding_mismatch`; no mutation |
| different owner/profile/workspace attempts attach | external `activation_invalid`; audit `foreign_owner`; no session metadata returned |
| activation expired | external `activation_invalid`; audit `activation_expired`; no attach |
| activation revoked/issuer-invalid | external `activation_invalid`; audit `activation_invalid`; no attach |
| session exists but no valid activation | external `activation_invalid`; audit `association_required`; no implicit discovery/ownership |
| association exists but session no longer resolves | mark `orphaned`; external `activation_invalid` on access; audit `association_stale`; preserve bounded lineage; no runtime action |
| session ends normally | mark `ended`; close observation only |
| Fleet record exists without valid Hermes provenance | external `activation_invalid`; audit `invalid_provenance`; quarantine/no forwarding |
| `fleet_owned_task` requested through v1 observer path | external `activation_invalid`; audit `capability_denied`; no mutation |

Errors are bounded and must not disclose prompt, history, provider, credentials, tool data, or terminal content.

## 6. Lineage fields

Every Fleet association/task record that refers to Hermes MUST retain:

- `association_ref`;
- `session_ref`;
- `activation_ref`;
- `owner_ref`;
- `profile_ref`;
- `workspace_ref`;
- `ownership_mode`;
- `source_system = hermes_gateway` for native Gateway events, or `source_system = pd_fleet` with `event_origin = fleet_reconciled` for Fleet-derived records;
- `provenance_ref`;
- `created_at`, `expires_at`, and `detached_at` when applicable.

These are opaque/bounded references. They do not authorize Fleet to read Hermes internals or PD Core decision content.

## 7. Open decisions carried to G3/G4

- exact Gateway operation that issues/validates activation;
- cryptographic or transport-level anti-replay mechanism;
- expiry/renewal policy and clock-skew tolerance;
- whether profile/workspace refs are Gateway-issued opaque refs or resolved through a separate identity service;
- audit retention and redaction of association history.
