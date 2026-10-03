# Gateway → Fleet Observer Bridge

Use this pattern when a user starts an interactive agent session and a coordination layer must become aware of it without owning the runtime.

## Architecture

```text
user-owned agent session → host gateway → observer/bridge → Fleet coordination → workflow/PD decisions
```

The dashboard is only one gateway client. Reuse the gateway protocol/event dispatcher, not dashboard UI code, routes, React state, or presentation-specific channels.

## Activation boundary

The Fleet client is activated from an explicit user action inside a Hermes session: the user starts Hermes and submits a PD goal or explicit Fleet coordination request. Hermes emits a bounded activation/association signal and the external Fleet client registers for that intended session. Do not parse arbitrary prompt text or passively claim every user-owned session. Activation identifies association; it does not grant control.

Keep the activation signal separate from the event stream. The initial event set should be metadata-only lifecycle/operational state:

- `session.registered`
- `session.status_changed`
- `session.heartbeat`
- `session.metadata_changed`
- `session.detached`
- `session.ended`

Exclude raw prompts, history, tool output, provider responses, credentials, and terminal frames from the v1 contract. If PD needs a goal reference, pass a bounded `goal_id`/association reference, not the full prompt.


## Discovery before implementation

Verify the actual host surface from source/docs:

- which clients use the gateway;
- whether standalone terminal sessions use the same gateway;
- whether event channels are PTY/chat scoped or global;
- authentication and owner/profile semantics;
- cursor/replay guarantees after reconnect;
- stable versus presentation-only payload fields.

Do not infer a global observer API from a dashboard-only subscription. If no supported global stream exists, propose a host-owned hook/channel in a separate scope.

## Contract boundary

Host/runtime owns concrete session, provider, tool, capability, and runtime state. The bridge owns translation, bounded persistence, correlation, cursor/checkpoint, reconnect reconciliation, and session/task association. The workflow control plane owns intent, contracts, gates, and human decisions.

Prefer a sibling gateway client/bridge as the first implementation. An in-process host hook can be a later optimization, but it increases coupling and blast radius.

## Safety defaults

Default-deny prompts, cancellation, provider activation, credentials, filesystem mutation, subprocess control, external messaging, and direct host-database writes. Prefer versioned gateway events and APIs over reading private host database schemas. Preserve the fake-only Fleet contract for later Fleet-owned execution.

## Verification

Use injected gateway doubles first. Test discovery, normalization, unknown/malformed events, duplicate events, gaps, reconnect, heartbeat expiry, stale sessions, owner mismatch, auth denial, and channel-scope mismatch. Require fresh documentation/path checks and `git diff --check`; do not claim live readiness from local fixtures.

See this file for the reusable pattern; keep session-specific source paths and evidence in the active project scope rather than copying them into the umbrella skill.
