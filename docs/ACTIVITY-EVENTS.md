# ACTIVITY-EVENTS — cross-runtime activity contract v1

Canonical description of the activity bus that feeds the fleet/swarm surface. Source of the
schema: `.spec/pd-fleet-control-plane-v1/ACTIVITY-CONTRACT.md` (mission contract); this page is
the stable, repo-level reference for consumers and future emitters.

Rule zero: **never fabricate telemetry** — no source, no event; a missing source renders as an
explicit `sem fonte`, never an invented row.

## Event schema (v1)

One JSON object per line (JSONL):

| field | type | req | notes |
|---|---|---|---|
| `v` | int | yes | schema version (`1`) |
| `event_id` | string | yes | stable unique id (`<agent>-<seq>` or uuid4) |
| `ts` | string | yes | ISO-8601 UTC of the *activity*, not of the write |
| `agent_id` | string | yes | emitting identity (`hermes:desktop`, `lane-codex-1`, ...) |
| `run_id` | string | yes | dispatch/run id; `solo` outside a run |
| `mission` | string\|null | no | PD mission slug when known |
| `source` | enum | yes | `hermes` · `fleet` · `kanban` · `monitor` · `external` |
| `fidelity` | enum | yes | `high` (native) · `partial` (derived: tail/RPC) |
| `kind` | enum | yes | `tool` · `file` · `status` · `heartbeat` |
| `action` | string\|null | no | tool/command name for `kind:tool` |
| `paths` | string[] | no | affected paths for `kind:file` (workspace-relative, redacted) |
| `status` | enum\|null | no | for `kind:status`: `running` · `waiting` · `done` · `failed` · `blocked` |
| `meta` | object\|null | no | small redacted scalars (counts, durations, model); never payload text |

Per-kind minimums: `tool` requires `action`; `file` requires at least one `path`; `status`
requires `status`; `heartbeat` needs only the base fields.

## Redaction (enforced at emit, re-asserted by consumers)

- Never emit secrets/tokens/keys, env values, credential paths, prompt or chain-of-thought text,
  URL query strings, message content or user ids.
- Paths stay workspace-relative; outside the workspace use `external:<scheme-or-host>`; truncate
  to 200 chars; never `/home/<user>/...`.
- `meta` holds scalars only (numbers or strings <= 80 chars), at most 8 keys, never nested payloads.
- Redaction is deterministic: same input state produces the same event apart from `ts`.

## Fidelity

- `hermes` session/bridge events, `fleet` run_store/AgentReport, `kanban`/`monitor` own metrics:
  `high` (native, structured).
- `external` lanes (log tail or RPC): `partial`; any uncertainty downgrades to `partial`.

## Transport and wiring (local v1)

- **Bus:** append-only JSONL at `~/.hermes/activity/events.jsonl`.
- **Watermark:** `~/.hermes/activity/state.json`, per `agent_id|run_id` last emitted `ts`; re-runs
  are idempotent (re-emitting the same window yields `skipped`, not duplicates).
- **Emitter:** `python3 scripts/pd_fleet/activity_emit.py [--dry-run] [--json]` — reads
  `~/.hermes/state.db` read-only (sessions, `messages.tool_name`, gateway heartbeats), local only,
  no network. Its window is *recent activity*: a session is only emitted when its last activity
  falls inside `WINDOW_HOURS` — a bulk `ended_at` alone does not qualify an old session.
- **Consumer:** `scripts/plan_cockpit_sync.py` (`_hermes_agents_from_events`) aggregates the bus
  into the swarm rows; an absent/empty bus stays an explicit `sem fonte`.
- The `pd-fleet-tui` wire remains a future transport for the same payloads; v1 does not require it.

## Freshness (consumer-side)

A status event is a claim about *now*, so the consumer re-checks age at render time:

- status-less `heartbeat` rows: `ok` within 5 min, otherwise `stale`;
- non-terminal status (`running`, `waiting`) older than 1 h: rendered `stale`;
- terminal status (`done`, `failed`, `blocked`) keeps its historical value.

Within one agent, the **most recent event wins**; rank only breaks ties on the same timestamp
(`failed` > `blocked` > `waiting` > `running` > `done`). A stale `running` must never mask a newer
`failed`.

## Consumers allowed in v1

Read-only surfaces only (Board fleet/swarm tab, Mission Control). No writer or steering consumer;
the steering contract is design-only until its own authorization.
