# B15a.2 — Hermes TUI session protocol seam

**Status:** discovery verified; implementation blocked at explicit RPC extension seam
**Scope:** documentation-only, read-only inspection of the installed Hermes TUI source/runtime
**Date:** 2026-07-31

## Decision

B15a.2 confirms the transport and session boundary needed for a future
`pd-fleet-hermes` TUI adapter, but does **not** activate the adapter or add a
live RPC. The current plugin contract remains lifecycle-only and default-off.

The TUI protocol is a host-owned seam:

```text
Hermes TUI (Ink/TypeScript)
        │ newline-delimited JSON-RPC 2.0 over stdio
        ▼
python -m tui_gateway.entry
        │ registered @method handlers
        ▼
tui_gateway.server
        │ Hermes-owned session/runtime state
        ▼
run_agent / Hermes plugins
```

## Observed runtime evidence

Inspection target:

- Hermes source: `/home/vitor/.hermes/hermes-agent`
- installed runtime: Hermes Agent `v0.18.2` (`e444d165`, local `3bb422a1`)
- TUI gateway package: `tui_gateway`
- active process observed: `python3 -m tui_gateway.entry`

The upstream TUI README documents:

- `hermes --tui` starts the Ink client;
- the client spawns `python -m tui_gateway.entry`;
- stdin/stdout carry newline-delimited JSON-RPC requests, responses, and events;
- stderr is captured separately as gateway diagnostics.

The inspected server registers session methods including:

```text
session.create
session.list
session.most_recent
session.resume
session.status
session.history
session.save
session.close
session.branch
session.interrupt
session.steer
session.cwd.set
session.active_list
session.activate
session.title
session.usage
session.context_breakdown
```

It also emits lifecycle/session events such as `session.info` and
`gateway.ready`.

## Plugin boundary

Hermes `PluginContext` exposes `register_hook(hook_name, callback)` and the
installed runtime recognizes `on_session_start` and `on_session_end`. The TUI
gateway calls the host plugin hook dispatcher at session boundaries.

The current `PluginContext` does **not** expose a method-registration API for
`tui_gateway.server`. The TUI RPC registry is defined by Hermes-owned
`@method("...")` handlers in `tui_gateway.server`; `plugins.manage` only lists
or toggles plugins and is not an extension point for arbitrary RPC methods.

Consequently:

- lifecycle observation is a valid B15a plugin capability;
- a namespaced RPC such as `pd-fleet.session.observe` cannot be claimed as
  implemented by the plugin package alone;
- adding such an RPC requires an explicit Hermes host seam (for example, a
  sanctioned RPC registration hook or a host-side bridge handler);
- modifying `~/.hermes`, the installed Hermes checkout, or the running TUI is
  outside this gate and requires a separate scope/approval.

## Proposed future RPC contract (not implemented)

If the host seam is approved later, the first method should be read-only and
single-session scoped, for example:

```text
pd-fleet.session.snapshot
```

Required properties:

- explicit `session_id` supplied by the host/client;
- no implicit "current session" lookup;
- no provider, prompt/history, credential, or dispatch payloads;
- bounded response size and field allow-list;
- capability check before invocation;
- stable JSON-RPC error for an unavailable/unauthorized seam;
- no Fleet-owned task creation or external effect;
- session association remains `user_owned_session` and read-only.

The exact method name and payload are intentionally undecided until the Hermes
host extension point is approved and tested against the actual TUI process.

## Verification and limits

Verified by source inspection and runtime process inspection only. No plugin was
installed or discovered by Hermes, and no config was changed. No RPC request
was sent to the running TUI gateway. No provider, network, credential,
subprocess dispatch, Gateway change, push, merge, release, or deploy occurred.

**Gate result:** `DISCOVERY_PASS / IMPLEMENTATION_BLOCKED_EXPLICIT_HERMES_RPC_SEAM`

The repository-side plugin remains a local reference package with
`default_enabled: false`, lifecycle hooks only, and zero tools.
