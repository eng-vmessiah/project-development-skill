# ACTIVITY-CONTRACT.md — v1 (T-101)

Cross-runtime activity events for the fleet workspace surface. Read-only consumers only in v1;
no action surface. Rule zero: **never fabricate telemetry** — no source, no event; explicit empty.

## Event schema (v1)

One JSON object per event, one per line (JSONL).

| field | type | req | notes |
|---|---|---|---|
| v | int | yes | schema version (`1`) |
| event_id | string | yes | stable unique id (`<agent>-<seq>` or uuid4) |
| ts | string | yes | ISO-8601 UTC, e.g. `2026-10-09T18:30:00Z` |
| agent_id | string | yes | emitting identity (e.g. `orchestrator-isis`, `lane-codex-1`) |
| run_id | string | yes | dispatch/run id; `solo` when outside a run |
| mission | string|null | no | PD mission slug when known |
| source | enum | yes | `hermes` | `fleet` | `kanban` | `monitor` | `external` |
| fidelity | enum | yes | `high` (native) | `partial` (tail/RPC-derived) — never `high` for derived data |
| kind | enum | yes | `tool` | `file` | `status` | `heartbeat` |
| action | string|null | no | tool/command name for `kind:tool` (`bash`, `edit`, `patch`, ...) |
| paths | string[] | no | for `kind:file`: affected paths (workspace-relative, redacted) |
| status | enum|null | no | for `kind:status`: `running` | `waiting` | `done` | `failed` | `blocked` |
| meta | object|null | no | small, redacted extras (counts, durations); never payload text |

Per-kind minimums: `tool` requires `action`; `file` requires `paths` (>=1); `status` requires
`status`; `heartbeat` needs only the base fields. Heartbeat cadence <= 60s per agent.

## Redaction rules (enforced at emit; re-asserted by consumers)

- Never include: secrets/tokens/keys, env values, credential paths, prompt or chain-of-thought
  text, URL query strings.
- Paths: workspace-relative only; outside workspace -> `external:<scheme-or-host>`; each path
  truncated to 200 chars; `/home/<user>/...` never emitted (use `~` only if unavoidable).
- `meta`: scalars only (numbers/short strings <= 80 chars), max 8 keys; never nested payloads.
- Redaction is deterministic: same input state -> same emitted event (no clocks beyond `ts`).

## Fidelity rules

- `hermes` session/bridge events: high (native, structured).
- `fleet` run_store events / AgentReport / checkpoints: high (ours, structured).
- `kanban`/`monitor`: high for their own metrics.
- `external` lanes (tail or RPC, e.g. omp `--mode rpc`): partial; set `meta.note` when derivation
  is uncertain. Uncertainty of ANY kind downgrades to partial.

## Source wiring (design; implementation T-201+)

| source | real feed | kinds |
|---|---|---|
| hermes | bridge/session events (observer transport) | tool, file, status, heartbeat |
| fleet | run_store events + AgentReport + checkpoints | status, heartbeat |
| kanban | worker heartbeats | heartbeat, status |
| monitor | machine-monitoring jsonl | status (host pressure) |
| external | lane logs tail / RPC | partial tool, status |

Empty semantics: a missing source renders as explicit "sem fonte" on the surface — never an
invented row (PLAN-COCKPIT golden rule).

Consumer allowlist (v1): read-only surfaces only (Board fleet tab, Mission Control). No writer or
steering consumer in v1.

## Fixtures

`fixtures/activity-events.example.jsonl` — deterministic, hand-written, one event per kind +
partial-external example. Validated by parse + required-key/enum checks (this repo session);
formal pytest lands with T-103.

## Local transport v1 (T-201)

- **Bus:** append-only JSONL at `~/.hermes/activity/events.jsonl` (one contract event per line).
- **Watermark:** `~/.hermes/activity/state.json` — per `agent_id|run_id` last emitted `ts`; re-runs are idempotent.
- **Emitter:** `python3 scripts/pd_fleet/activity_emit.py [--dry-run]` — reads `~/.hermes/state.db`
  READ-ONLY (sessions / messages.tool_name / gateway_heartbeats); never message content, never user ids;
  local only, no network. `--json` gives a machine summary.
- **Consumer:** `scripts/plan_cockpit_sync.py` (`_hermes_agents_from_events`) aggregates the bus into the
  swarm surface; an absent/empty bus renders as explicit "sem fonte".
- The `pd-fleet-tui` wire stays a future transport for the same payloads; v1 does not require it.
