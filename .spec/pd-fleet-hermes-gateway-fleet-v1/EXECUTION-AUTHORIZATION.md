# Execution Authorization — PD Fleet ↔ Hermes Gateway Fleet v1

**Authorized by:** Vitor (current session)
**Authorization:** execute the remaining project plan through local implementation, fake/injected Gateway validation, and closeout; prefer existing Hermes Gateway capabilities where they exist.
**Date:** 2026-07-29

## Allowed scope

- Implement Fleet-side read-only bridge code in this repository.
- Implement isolated fake/injected Gateway protocol fixtures.
- Add tests, schemas, redaction, replay, cursor, association, and persistence coverage.
- Add a read-only adapter for existing Hermes HTTP/session/run surfaces only where their actual contract is verified.
- Run local tests, fake canaries, static checks, and bounded smoke tests.
- Use subagents for implementation and independent review.

## Explicit boundaries

- No modification of the Hermes Agent checkout in `/home/vitor/.hermes/hermes-agent` during this wave.
- No automatic Hermes Gateway start/restart/reload.
- No live provider calls, prompt dispatch, tool execution, session mutation, cancellation, credentials, or external messaging.
- No use of dashboard `/api/events?channel` as a global Fleet contract.
- No invention of unsupported `fleet.*`/`pd.*` Hermes APIs.
- No claim that the existing Hermes surfaces support global Fleet subscription or activation tickets.
- `fleet_owned_task` remains denied.

## Real Hermes adapter policy

The real adapter may use existing, verified read-only Hermes surfaces such as authenticated session/run inspection or bounded run event streaming. It MUST return an explicit `NOT_READY_HERMES_SEAM` result when the requested operation requires an unsupported global observer, activation ticket, association, replay, or subscription seam.

## Acceptance status

This authorization permits local implementation and verification. It does not authorize production, live Gateway integration, runtime control, provider activation, release, merge, or push. Final status must distinguish:

- local implementation verified;
- fake Gateway end-to-end verified;
- existing Hermes read-only adapter verified;
- Hermes Fleet observer seam not ready.
