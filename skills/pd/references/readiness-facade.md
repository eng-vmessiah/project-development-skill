# Readiness composition → Supervisor facade

Reusable closeout pattern for a derived, read-only readiness surface.

## Boundary order

```text
already-materialized reports
  → pure ReadinessView composer
  → thin Supervisor facade
  → dedicated CLI (optional later gate)
```

Do not make the composer read `STATE`, filesystem, providers, network, or process state. It should accept exact report types, return frozen/detached data, and expose only fixed safe reason codes.

## Precedence

1. Supervisor `blocked`, `failed`, or `needs_human_intervention` → `blocked` / `supervisor_blocked`.
2. Supervisor `degraded`/`slow`, or event/reconciliation `degraded` → `degraded` / `source_degraded`.
3. Supervisor `suspected`, or event/reconciliation `unknown` → `unknown` / `missing_or_unknown_source`.
4. Healthy/consistent supplied reports → `ready`.
5. No supplied reports → `unknown`.

Validate the component status enums and coherence between aggregate status, reasons, and `present_components`; reject arbitrary status strings and inconsistent manually constructed views.

## Facade contract

The Supervisor method should be a keyword-preserving one-call delegation to the composer. Verify:

- exact result equality and exception equivalence;
- no dispatch-count/state mutation;
- no filesystem/provider/network/process/`PDState` access;
- no leakage of raw reasons, proposals, owners, task IDs, or payloads;
- frozen/detached JSON remains intact.

## Review probes

Run focused and full tests, `compileall`, and `git diff --check`. Separately inspect the import graph: importing the pure composer should not transitively load heavy Supervisor/run-store modules when lazy imports/`TYPE_CHECKING` can avoid that. Use hostile report objects, invalid enums, duplicate/oversized tuples, precedence combinations, mutation of returned dictionaries, and source inspection for forbidden integrations.

## Planning artifact pitfall

When updating a long plan/checkpoint with targeted replacement, include the section heading in the match and re-read the affected range. Broad replacement can silently delete the preceding gate; code tests will not detect damaged planning state.
