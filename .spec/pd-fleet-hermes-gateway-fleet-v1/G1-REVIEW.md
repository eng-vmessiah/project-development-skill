# G1 — Independent Review

**Status:** `local_verified_live_open`
**Scope:** local/fake/injected implementation and verification; live Hermes seam excluded
**Reviewed:** `G1-CONTRACT.md`, `G2-OWNERSHIP.md`, `G4-SECURITY.md`, `PLAN.md`, `README.md`, `DISCOVERY.md`, `STATE.md`
**Implementation authorization:** local/fake/injected only; no live runtime/production

## Confirmed

- Architecture is consistent:

  ```text
  Hermes Runtime / Session
    → Hermes Gateway
    → Fleet Gateway Bridge
    → PD Fleet
    → PD Core
  ```

- Hermes/Gateway remains authoritative for concrete runtime/session state and native event delivery.
- Fleet Bridge is a translation seam, not a second runtime authority.
- PD Fleet owns coordination, association, lifecycle, leases, checkpoints, reconciliation, and reports.
- PD Core owns goal, SPEC, PLAN, DAG, acceptance, gates, human decisions, and merge/release decisions.
- Activation/association is separate from event observation.
- Initial association is `user_owned_session`, read-only/default-deny.
- `fleet_owned_task` remains future and separately authorized.
- Initial event allowlist is lifecycle/operational metadata only.
- Prompts, history, tool data, provider responses, credentials, terminal frames, and arbitrary message content are excluded.
- Malformed/unknown/unsupported/oversized data fails closed.
- Local review and implementation evidence are complete for the authorized fake/injected path; the Hermes owner, security, and live-seam decisions remain open.
- Live Hermes runtime/Fleet observer activation/global subscription/opaque issuer/production remain `NOT_READY` (`NOT_READY_HERMES_SEAM`).
- G8 remains `local_closeout_not_promotable`; no promotion or live security closure is claimed.

## Blockers carried into G1/G4

1. The exact Hermes-owned transport/extension that will issue activation and serve `fleet.connect`/`fleet.subscribe` remains unresolved.
2. The activation artifact requires a concrete transport authentication and replay-protection mechanism.
3. Enum values, cardinality/range limits, payload byte limits, and redaction rules must be frozen in the security/capability gate.
4. No Gateway observer authorization may be interpreted as runtime authorization.
5. Final enum values, bounds, redaction tests, and owner-provided closure evidence remain open; G2/G4 are drafts, not passed gates.

## Read-only Hermes seam evidence

Inspection of `/home/vitor/project/hermes-agent-routing` confirmed:

- `tui_gateway/ws.py` exposes the existing `/api/ws` transport and reuses the newline-delimited JSON-RPC dispatcher.
- The current Gateway emits `gateway.ready` and existing runtime/session/tool/message events for current clients.
- `hermes_cli/web_server.py` implements `/api/events` as an in-memory channel publisher/subscriber for dashboard/PTY surfaces.
- The existing dashboard surface has a session-token/auth boundary, but no Fleet-specific client authorization or owner/profile/workspace binding.
- No `fleet.*`, `pd.*`, `subscribe`, or `register` method was found in `tui_gateway/server.py`.

This evidence supports the live-seam hold: the Gateway is the correct host seam, but `fleet.connect`/`fleet.subscribe` are proposed extension points, not currently supported Hermes APIs. Local/fake/injected implementation and verification do not establish a supported current Hermes API, and no Hermes repository change was made.

## Decision

`PASS_WITH_BLOCKERS` for the locally authorized fake/injected implementation and verification, with live Hermes owner/security/seam decisions still open. The packet does not establish a supported current Hermes API, does not claim G4 live security closure or G8 promotion, and does not authorize provider access, network exposure, dispatch, or production use.
