# PD Fleet → Hermes Gateway Fleet Bridge v1 — Scope and Local Status

**Current outcome:** local/fake/injected implementation verified; live Hermes Fleet seam `NOT_READY_HERMES_SEAM`.

This spec authorizes a bounded local read-only Fleet bridge and deterministic fake/injected Gateway validation. It does **not** authorize production, live Gateway connection, provider activation, credentials, session mutation, dispatch, merge, release, or a live-readiness claim.

## What exists

- Versioned bridge, ownership, delivery, and security contracts in this directory.
- Local fake Gateway and Fleet bridge artifacts under `scripts/pd_fleet/`.
- Existing Hermes read-only adapter: `scripts/pd_fleet/hermes_existing_adapter.py`.
- Deterministic fake/injected coverage: 45/45 G5 scenarios, including 44 distinct negatives; full suite evidence is recorded in `VERIFICATION.md`.

## Hermes boundary

The existing adapter wraps only an explicitly injected, verified read-only Hermes client. It does not provide Fleet observer activation, global subscription, Gateway-owned association, opaque activation-ticket issuance/consume/revoke, issuer verification, or a durable Fleet replay seam. Unsupported operations fail closed with `NOT_READY_HERMES_SEAM`.

The dashboard channel is not a global Fleet contract. The TUI backend (`tui_gateway.entry` / `tui_gateway.server`) is a separate local JSON-RPC/stdio caller and is now the planned first B15 seam, limited initially to the active session. It is not implemented or wired yet, does not provide global observation, and does not solve the messaging Gateway path. Both seams remain a Hermes owner/security responsibility requiring separate implementation, review, authorization, and validation.

## Authority and modes

Hermes owns runtime/session state; Fleet owns coordination state; PD Core owns intent and gates. `user_owned_session` is read-only by default. `fleet_owned_task` remains separately authorized and denied in this scope.

See `PLAN.md`, `STATE.md`, `VERIFICATION.md`, `CLOSEOUT.md`, and `EXECUTION-AUTHORIZATION.md` for the evidence map, blocker, and non-promotion decision.
