# D7 — B15a.2 Limited Implementation Authorization Request

**Status:** `PENDING_VITOR_APPROVAL`  
**Preconditions:** D1–D6 approved in `B15A-DECISION-MATRIX.md`.

## Requested authorization

Authorize B15a.2 implementation only as a local, default-off, read-only TUI seam slice.

### Proposed execution boundary

- **Hermes worktree:** `/home/vitor/project/hermes-agent-b15a-rpc-seam`
- **Branch:** `feat/b15a-rpc-seam` or a new explicitly named child branch from its verified local checkpoint
- **Fleet repository:** `/home/vitor/project/project-development-skill`, branch `feat/pd-hermes-gateway-fleet-v1`
- **Allowed changes:** approved seam registration/dispatch, lifecycle-only plugin integration, server-side session binding adapter, closed schemas, injected/fake fixtures, tests, docs.
- **Required verification:** RED-first tests; absent/disabled/non-Fleet compatibility; identity/default-deny; schema/redaction; replay/recovery/lifecycle tests; independent review; compile/diff/doc gates.

### Explicitly forbidden

- modifying canonical `/home/vitor/.hermes/hermes-agent` checkout;
- plugin installation/discovery in active runtime;
- Gateway/TUI start, restart, reload or runtime configuration change;
- live provider/network/credential use;
- tool execution, prompt dispatch, task dispatch, session mutation or cancellation;
- external messaging;
- push, merge, release, deploy.

### Rollback

All code stays in isolated worktrees/branches. Rollback is reverting isolated commits or deleting the unmerged branch; no active runtime state can be left behind because activation is forbidden.

## Expected outcome

At most `LOCAL_SEAM_VERIFIED / LIVE_NOT_READY`. This authorization does not approve live Hermes readiness or B15b.
