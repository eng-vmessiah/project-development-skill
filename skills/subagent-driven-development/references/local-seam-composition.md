# Local seam composition with subagents

Use this pattern when two independently tested, local/default-off components must compose before any runtime activation.

## Sequence

1. **Discover both real contracts in parallel.** One reviewer maps host registry/dispatcher handler arity and return semantics; another maps the client bridge registrar port and closed request schemas; a third lists security acceptance and prohibited claims.
2. **Do not let a fake improve the real contract.** The in-memory dispatcher must preserve the observed host handler signature and raw-return behavior. If composition reveals an envelope mismatch, stop the canary and correct the production-side boundary first.
3. **TDD each wire correction.** Add a RED test for the actual mismatch, then implement the smallest bounded helper and run focused tests before broader gates.
4. **Validate JSON-RPC IDs before all side effects.** Only permit `str`, non-boolean integral numbers, finite floats, or `null`; malformed IDs return a bounded `Invalid Request` JSON-RPC error with `id: null`, and must not trigger local detach/revoke callbacks.
5. **Canary acceptance.** Prove disabled means no publication; enabled means the exact allowlisted methods in deterministic order; dispatch uses closed schemas; client-supplied identity/capability fields deny; registrar errors are normalized without secret reflection; valid results are bounded JSON-RPC envelopes.
6. **Close in waves.** Parent verifies focused suite + full relevant suite + compile/diff checks. Then use separate security/spec and quality reviewers. Commit code first, document the verified local state second.

## Scope labels

A fake/injected composition can substantiate `LOCAL_SEAM_COMPOSED` only. It must retain `LIVE_NOT_READY`: it does not prove plugin discovery, runtime registration, live TUI/Gateway, host identity resolution, durable replay/outbox, network effects, or operational rollback.

## Avoid

- Do not start a runtime just to test registry composition.
- Do not import the host runtime into the client-side bridge merely to gain test coverage.
- Do not claim host exception-envelope parity unless the host dispatcher was directly included or its exact behavior is observed.
- Do not reflect raw request fields, cursors, identities, or exceptions in output envelopes.
