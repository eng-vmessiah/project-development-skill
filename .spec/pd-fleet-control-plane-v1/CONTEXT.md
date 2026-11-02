# Context — pd-fleet-control-plane-v1

## Source of truth

- Owner vision (09/10/2026): vault `Projects/project-development-skill/control-plane-workspace.md`.
- Repo input: `ROADMAP.md` -> "Fleet harness research inputs — oh-my-pi (omp)" (+ Mapping).
- Existing machinery: `scripts/pd_fleet/` (supervisor/observer, read-only increment);
  `scripts/plan_cockpit_sync.py` (collector + mc widgets); `docs/PLAN-COCKPIT.md`; board
  connector / tool-mode pattern (commit `fc6e618`); war-room / Swarm Kanban (frontend track).
- State: `.spec/pd-fleet-control-plane-v1/`.

## Decisions

- D-001 — The workspace view is a **surface over real state**, not a new source of truth.
  Sources: fleet run_store/observer events, kanban heartbeat, machine monitor, plan.yaml/STATE.
  Golden rule: never fabricate telemetry.
- D-002 — **Read-only first.** Supervisor remains control-plane, not executor; v1 ships zero
  action surface. Steering is contracted (R4) but implemented only under separate
  authorization (default-deny).
- D-003 — **Cross-runtime activity contract** (R1) is the new core piece; fidelity is
  progressive and labeled per source (native Hermes = high; external lanes = partial).
- D-004 — Visual surfaces: extend `mc`/`fleet` Board tabs first (live bindings proven);
  war-room is the later full-swarm canvas. No parallel dashboard platform.
- D-005 — omp/oh-my-pi is UX/feature reference only (roster/cost/time, live transcript,
  steer/revive/kill, `agent://` addressing); not installed, not integrated, not authoritative.

## T-202 review — findings and dispositions (02/11)

Verdict: **APPROVED WITH RESERVATIONS** (no BLOCKER/HIGH). The reviewer recomputed the
artefacts; the orchestrator re-executed every claim against the live files before acting.

- **RISCO-1** (stale `running` rendered as current) — fixed: non-terminal status (`running`,
  `waiting`) older than `STATUS_FRESH_S` (1 h) renders `stale`; heartbeat rows keep the 5 min
  rule. Evidence: `scripts/plan_cockpit_sync.py`, test
  `test_collector_downgrades_old_running_to_stale`; live `swarm/agents.md` now shows
  `hermes:desktop stale` (was `running`, hb 09/10).
- **RISCO-2** (rank could mask a newer failure) — fixed: the newest event wins; rank only breaks
  same-timestamp ties (`failed > blocked > waiting > running > done`). Test:
  `test_collector_newest_event_beats_older_rank`.
- **RISCO-3** (emitter window keyed on `ended_at`, not activity) — fixed: an event whose emitted
  `ts` falls outside `WINDOW_HOURS` is skipped. Test:
  `test_activity_emit_window_uses_activity_not_ended_at`; the live dry-run no longer proposes
  the six 10/07 events.
- **RISCO-4** (R1 also requires `docs/`) — fixed: `docs/ACTIVITY-EVENTS.md` (contract v1,
  redaction, transport, consumer freshness) linked from `docs/PLAN-COCKPIT.md`.
- **NIT-1** (RESULTS listed 15 of 18 without saying so) — fixed in the generator and annotated in
  `spike-laya/RESULTS.md`.
- **NIT-2** (heartbeat fixture carried `status`) — fixed: `demo-0004` matches the per-kind
  minimum (heartbeat = base fields).
- **NIT-3** (`~/.venvs/pd` has no pytest) — fixed in the wrapper comment; tests run with
  `/usr/bin/python3 -m pytest`.
- **NIT-4** (`pd validate` 10/11, no `VERIFICATION.md`) — expected; deferred to T-401.

Rulings: (a) staleness also covers `waiting` — a non-terminal status is a claim about "now", so
the same deception applies; cost if wrong: an idle-but-open session shows `stale` after 1 h.
(b) events already in the bus are **not** rewritten — telemetry is append-only; the emitter stops
producing old ones and the consumer labels terminal rows historically.

Delta verification: `pytest tests/ -q` 1434 passed / 1 skipped; `uvx ruff check` on the touched
files equal to baseline (21 pre-existing, zero new); live publish re-run and inspected.
Independent second-pass review of the delta stays open for T-401.

## Status labels

`implemented`, `verified`, `deferred`, `blocked` are distinct; without human gate approval the
state is `NOT READY/PARTIAL`, never PASS.
