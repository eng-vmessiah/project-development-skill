# D0 Surface Comparison — Real Hermes Adapter

**Scope:** `pd-fleet-hermes-adapter-real-v1`
**Mode:** discovery-only
**Decision:** `HOLD_SURFACE_UNCONFIRMED`
**External effects:** disabled

## Executive conclusion

No currently observed Hermes surface is a complete Fleet task bridge.

| Candidate | What it actually provides | Fleet fit | Decision |
|---|---|---:|---|
| Direct internal `delegate_task` / `parent_agent` call | Internal agent-loop tool requiring live `AIAgent` context | Low | Reject as external adapter API |
| ACP | Host-controlled conversational sessions over stdio, prompt, updates, cancel, load/resume/fork | Medium for session host; low for child-task lifecycle | Do not adopt as Fleet contract; possible transport under a future adapter |
| Hermes MCP server | Conversation/message/event/permission tools | Low for execution; useful for observation/notification | Reject as execution bridge |

## Candidate 1 — direct `delegate_task`

The local Hermes source contains a real `delegate_task` tool implementation, but it requires internal `AIAgent` parent context and participates in the agent loop. No stable host API was found that accepts a Fleet-shaped delegation request and returns a typed child-task lifecycle.

Calling internal functions, global child registries, completion queues, or `handle_function_call` outside the agent loop would create unsupported coupling and would not satisfy Fleet guarantees for timeout, cancellation confirmation, handoff, cleanup, replay, or fencing.

**Verdict:** reject as the primary external integration seam.

## Candidate 2 — ACP

ACP provides the strongest host/session surface observed:

- `session/new`, `session/prompt`, `session/cancel`;
- load/resume/fork/list capabilities in Hermes;
- streamed `session/update` events;
- injected agent/database seams for tests;
- local stdio transport.

However, ACP models a conversational agent session, not a Fleet task:

- no `run_id/task_id/attempt_id` contract;
- no lease/generation fencing;
- no idempotency/fingerprint;
- no normative timeout result;
- no confirmed cancellation/termination reference;
- no Fleet handoff artifact;
- no orthogonal cleanup contract;
- no durable Fleet event cursor/replay.

A future adapter could use ACP as a transport, but Fleet must remain the source of truth and own all missing lifecycle semantics. ACP dependencies are not installed locally, and installing them is outside this discovery scope.

**Verdict:** possible transport under a future adapter; not the Fleet contract and not ready for implementation authorization.

## Candidate 3 — MCP

The observed Hermes MCP server exposes conversation, message, attachment, event, channel, and permission tools. It does not expose submit-task, delegate, cancel-task, handoff, or cleanup operations. Its event queue is bounded/ephemeral and is not a durable Fleet event log.

MCP `messages_send` can have external messaging effects, while the server does not provide Fleet owner/run authorization, fencing, receipts, or replay semantics.

**Verdict:** reject as the execution bridge. It may be considered later for read-only observation or human notification, under a separate capability scope.

## Decision

`D0.2` remains `HOLD_SURFACE_UNCONFIRMED`.

Before designing the bridge contract, one of these must be established from supported Hermes host documentation/code:

1. a public host-side delegation API with child lifecycle control; or
2. an explicitly supported way to host a Hermes session through ACP/API while accepting that Fleet owns the child-task lifecycle externally; or
3. a new Hermes-owned bridge contract designed specifically for Fleet, with submit/status/cancel/handoff/cleanup semantics.

No implementation, dependency installation, provider readiness check, config change, server start, credential access, or live dispatch is authorized by this comparison.
