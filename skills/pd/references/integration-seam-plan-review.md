# Integration-Seam Plan Review

Use this checklist before implementing a wave that depends on an external runtime, plugin API, RPC seam, or owner-controlled checkout.

## Gate

Run two independent reviews in read-only mode. Keep review status separate from human approval, implementation authorization, and runtime readiness.

## Checklist

1. **Verify the seam as fact.** Inspect the real owner checkout or authoritative source. Distinguish existing APIs from proposed APIs. If the public seam is absent, mark dependent work blocked; do not use internals or infer support from fake/local tests.
2. **Reconcile vocabulary.** Cross-check method names and lifecycle terms across plans, contracts, schemas, fixtures, and prior scopes. Names such as `activate/status/deactivate` and `connect/subscribe/disconnect` must be mapped explicitly or treated as a blocker.
3. **Make acceptance measurable.** Freeze byte/depth/cardinality/TTL/replay bounds, cursor/gap/epoch semantics, error envelopes, authentication and owner binding, crash/restart behavior, and named commands/artifacts for verification.
4. **Model default-deny composition.** Define precedence for absent, malformed, disabled, partially enabled, hot-reloaded, and direct-dispatch paths. Every relevant method must enforce the same server-side policy.
5. **Separate loading from runtime registration.** Lifecycle-only plugin loading must not implicitly register RPC handlers, attach sessions, persist state, access credentials, or use network/provider/subprocess capabilities.
6. **Specify identity operationally.** Define the trusted caller source, process/transport binding, active-session resolution, owner/profile/workspace binding, reconnect, multiple sessions, and foreign-owner rejection.
7. **Close lifecycle semantics.** Define the authority and state transitions for attach, detach, session end, normal exit, crash, restart, in-flight calls, stale epochs, and orphan cleanup.
8. **Preserve honest readiness.** Local/fake evidence proves only the inspected local boundary. Keep live integration `NOT_READY` until the real seam, identity, security review, owner authorization, and bounded real-path evidence exist.

## Review verdict

Use `PASS`, `PASS_WITH_BLOCKERS`, or `HOLD`. A missing public seam, invented API, unresolved contract vocabulary, non-measurable security criterion, or ambiguous identity/restart behavior blocks implementation. Record findings with severity and file/line references; do not edit the owner checkout during review.
