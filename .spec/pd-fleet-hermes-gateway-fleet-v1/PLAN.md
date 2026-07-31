# PD Fleet → Hermes Gateway Fleet Bridge v1 — Execution Plan

> **Execution mode (authorized):** local Fleet-side implementation and verification are authorized with deterministic fake/injected Gateway fixtures. The existing Hermes read-only adapter may use only verified existing surfaces. **Live Hermes Gateway Fleet activation, global subscription, association, opaque-issuer/ticket seam, and production promotion remain `NOT_READY`.** See `EXECUTION-AUTHORIZATION.md`.

> **Integration boundary:** this directory tracks the optional `pd-fleet-hermes` Hermes plugin/adapter. It is not the Fleet Core, and its absence must not break `pd-only` or `fleet-local`. The plugin remains default-off and live Hermes activation remains separately gated.

## Goal and boundaries

Implement and verify the smallest read-only Fleet bridge locally without inventing Hermes APIs. Hermes owns concrete runtime/session state; Fleet owns coordination state; PD Core owns intent, gates, and human delivery decisions. No provider calls, credentials, subprocess control, live dispatch, session mutation, or release/merge claim is authorized.

## Evidence map

| Gate | Current evidence | Status |
|---|---|---|
| G0 | `DISCOVERY.md`: dashboard channel is not a global Fleet contract; live surface/issuer seam remains unconfirmed | `HOLD` |
| G1 | `G1-CONTRACT.md`, `G1-REVIEW.md`; versioned bounded lifecycle event contract | `local_verified` |
| G2 | `G2-OWNERSHIP.md`; ownership and association rules implemented/tested locally | `local_verified` |
| G3 | `G3-DELIVERY.md`; cursor/replay/reconnect/stale semantics and fixture coverage | `local_verified` |
| G4 | `G4-SECURITY.md`, `G4-CLOSURE.md`, `G4-AUTH-LIFECYCLE.md`; local policy/negative coverage, Hermes owner/security decisions still open | `local_verified_live_auth_open` |
| G5 | fake/injected matrix: 45/45 scenarios, 44 distinct negatives; direct/module deterministic | `local_fake_verified` |
| G6 | local bridge and existing read-only adapter; unsupported Fleet operations return `NOT_READY_HERMES_SEAM` | `local_injected_verified_live_not_ready` |
| G7 | isolated fake Gateway canary is deterministic and no-live-effect | `local_fake_canary_verified` |
| G8 | this reconciliation and `CLOSEOUT.md`; implementation is locally closed but not promotable | `local_closeout_not_promotable` |

## Execution sequence

1. Preserve the G0 finding: do not treat dashboard `/api/events?channel` as Fleet-wide discovery.
2. Keep G1–G4 contracts and security constraints as the authority for local doubles.
3. Verify the fake Gateway, bridge, redaction, ownership, cursor/replay, and failure behavior with injected tests.
4. Verify the existing Hermes adapter only on declared read-only surfaces; return `NOT_READY_HERMES_SEAM` for missing global observer/activation/replay/subscription capabilities.
5. Run the full local suite and documentation checks; record exact outputs in `VERIFICATION.md`.
6. Treat the local TUI backend (`tui_gateway.entry` / `tui_gateway.server`) as the first candidate Hermes caller for the next live seam. The TUI path uses local newline-delimited JSON-RPC over stdio and must begin with one authenticated, server-resolved active session; it is not the messaging Gateway and is not a global Fleet source.
7. Keep B15a as a separate, default-off local/injected wave, but do not implement it while `B15A-EXECUTION-PLANS.md` is `blocked_pending_plan_approval`. First obtain review closure for the public Hermes/TUI namespaced-RPC seam, identity binding, composite default-deny policy, closed redacted schemas/bounds, and replay/restart semantics. Only then implement and test B15a.0; the plugin contract begins with `plugin.yaml` + `register(ctx)` and lifecycle hooks only; no model-invocable tools, auto-install, plugin-directory persistence, global import shims, network, credentials, provider, or subprocess side effects. Then implement TUI activation/status/deactivation RPC, backend-owned principal/capability resolution, session-scoped attach, bounded redacted events, cursor/replay, detach, session-end cleanup, and crash/restart invalidation. Keep `NOT_READY_HERMES_SEAM` until the actual TUI path and security policy are tested.
8. Only after B15a local approval, evaluate B15b for the messaging/API Gateway: authenticated caller, multi-session/global subscription, durable association/replay, transport auth, and operational rollback. B15b is a separate owner/security decision.
9. Close G8 as a local evidence closeout only. Do not promote, merge, release, activate providers, or claim live Hermes readiness.

## Promotion gate

Promotion is **not approved**. B15a TUI work may reduce the first integration surface, but it does not authorize the messaging Gateway or production. Before any live Hermes claim, the Hermes owner and security owner must provide an implemented and reviewed TUI activation/association seam, then the separately reviewed messaging-Gateway registration/activation, subscription, issuer verification, durable replay/association, transport authentication, redaction, and operational rollback seams, followed by separately authorized live validation. Until then the authoritative outcome is `NOT_READY_HERMES_SEAM` / `HOLD_UNRESOLVED` for live integration.

## Verification requirements

- facts, local evidence, limitations, and open decisions remain separated;
- fake/injected tests do not imply live Hermes support;
- docs/path checker passes;
- `git diff --check` passes;
- no production, merge, release, or live-dispatch decision is implied.
