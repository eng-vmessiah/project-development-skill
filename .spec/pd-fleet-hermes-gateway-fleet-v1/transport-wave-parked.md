# HTTP/SSE Transport Wave — Parked / Rejected

**Status:** `parked_security_rejected`
**Selected direction:** dedicated API server HTTP/SSE + Hermes-issued `pd-fleet` audience
**No merge/push/runtime activation:** yes

## Why it was parked

The experimental transport adapter passed 7 happy-path tests but failed adversarial review. It is not an approved transport foundation.

Blockers found:

- ticket store did not cap active tickets;
- public `issue_ticket()` relied on convention instead of an internal capability boundary;
- HTTP handler accepted caller-supplied Python `FleetTicketBinding` objects as authorization;
- registration was unbounded and not used as an authorization source;
- snapshot/stream/detach did not require a server-side consumed-ticket association;
- status reported `READY` merely from config, without route wiring/auth/writer readiness;
- hub and transport enabled states could diverge;
- SSE did not parse/validate HTTP cursors or replay gaps;
- SSE queue could silently evict events;
- event serialization dropped metadata and emitted incomplete IDs;
- HTTP body/path/reference validation was insufficient.

## Disposition

Do not wire routes, do not enable the feature, do not apply this experimental transport code to the active runtime, and do not include it in the replayable Hermes patch.

The only approved Hermes artifact remains:

- commit `7e27e622e4`
- patch `patches/0001-fleet-observer-contract.patch`

## Required redesign before another transport attempt

1. Server-side attachment registry keyed by authenticated principal + consumed ticket + association.
2. Internal-only ticket issuance capability; HTTP cannot supply claims or binding objects.
3. All association operations require an attached server-side association.
4. Explicit disabled/unwired status must remain `NOT_READY`.
5. Bounded ticket, observer, attachment, SSE queue, and event retention state.
6. HTTP JSON parsing and bounded reference/body validation.
7. Complete cursor/epoch/sequence HTTP contract with explicit gap/resync.
8. No silent SSE eviction; backpressure or explicit overflow/gap event.
9. Full metadata-only event envelope serialization.
10. API-server route wiring only after a separate Hermes owner/security gate and tests against the actual server lifecycle.
