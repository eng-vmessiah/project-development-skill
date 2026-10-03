# PD Runtime Adapters and Hermes Plugin Boundary

Use this reference when designing or implementing PD Fleet integrations with Hermes or other runtimes.

## Core rule

Hermes adds capabilities to Fleet; Hermes does not define what Fleet is.

Keep three modes explicit:

- `pd-only`: spec, plan, DAG, contracts, gates, evidence, and human decisions; no Fleet or runtime required.
- `fleet-local`: local/simulated scheduling, lifecycle, reports, checkpoints, and resume; must work without Hermes, credentials, network, or providers.
- `fleet-hermes`: optional Hermes runtime adapter, preferably packaged as an opt-in `pd-fleet-hermes` plugin.

## Plugin boundary

The Hermes plugin is a thin integration layer. It may register tools, slash/CLI commands, lifecycle hooks, and translate an authenticated Hermes session into the generic runtime-adapter contract.

Keep these outside the plugin:

- Fleet scheduler and DAG evaluation;
- Fleet persistence and checkpoints;
- generic gates and evidence policy;
- generic lifecycle, reports, retry, and resume;
- local adapter behavior.

The plugin is not required for `pd-only` or `fleet-local`, and a disabled/missing plugin must not break those paths.

## Capability-first behavior

Select runtimes explicitly (`none`, `local`, `hermes`, future OpenCode/Claude/other adapters). If a runtime lacks a requested capability, block with an actionable unsupported-capability result. Do not silently require Hermes or emulate Hermes-only session semantics in the local adapter.

Plugin enablement is not live authorization. External effects still require Fleet flags, evidence gates, security review, rollback, and explicit approval.

## Hermes Fleet sequence

- B15a: `pd-fleet-hermes` plugin + TUI backend, initially one active session through the existing JSON-RPC/stdio path.
- B15b: the same plugin + messaging/API Gateway, separately reviewed for multi-session/global subscription.

The TUI/Gateway integration is an optional adapter track, not a prerequisite for closing the local Fleet.
