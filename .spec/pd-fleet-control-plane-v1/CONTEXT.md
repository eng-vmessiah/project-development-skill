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
Second pass closed: the reviewer confirmed the delta on 02/11 (`evidence: 9f60af3/961da60`) and
closed T-202 on their side; the notify wording (`15/21` = agreement at threshold 0.5, not 15
events with p>=0.5) is confirmed as read. T-401 keeps NIT-4.

## Status labels

`implemented`, `verified`, `deferred`, `blocked` are distinct; without human gate approval the
state is `NOT READY/PARTIAL`, never PASS.

## T-301 — steering contract (02/11)

- Deliverable: `STEERING-CONTRACT.md` (419 lines) — five verbs (steer/pause/resume/kill/retry),
  tiers T0–T3 default-deny, command envelope with idempotency key, `owner_epoch` fencing,
  owned vs attached targets, hash-chained audit, explicit "design only, zero action surface".
- **D-006** — `resume` is a first-class verb: a pause without an exit pushes operators into `kill`.
- **D-007** — a verb's effect is observed through the sink's health snapshot first and the R1 bus
  second; R1 `kind:status` has no `paused`/`cancelling`/`cancelled`, so extending the enum (or
  echoing `command_id` in `meta`) is a named v2 requirement, not something v1 pretends to have.
- Grounding is executable, not prose: `steering/probes/run_probes.py` → `TOTAL=6 PASS=5 FAIL=1`.
  The single FAIL is the refuted claim kept on purpose — `sandbox.py` refuses URLs in `env` and
  redacts them in output, but **accepts a URL inside an allowlisted argv**, so it is not a network
  boundary. §8/§10 were corrected instead of quietly dropping the claim.
- Review chain (house rule: reviewer from a different family than the author):
  GLM-5.3-Flash via OpenCode → **PASS_WITH_RESERVATIONS** (0 BLOCKER, 1 HIGH, 3 MEDIUM, 2 LOW,
  1 NIT) → all seven disposed → **Vigia** (role `Revisor PD`, on the Maestri canvas) delta review
  → **PASS**, 6/7 CLOSED, ST-06 CLOSED with a wording reservation, 2 new NITs both fixed.
- Commits `4c2876f` + `f35a743` on `feat/pd-t301-steering`, landed on `main` by fast-forward.
  Zero action surface shipped: `CAPABILITIES_V1` is still `{"observation"}` (probe-confirmed).

## T-402 — collector counts `completed` as terminal (02/11)

- Root cause found by the closeout audit (independent subagent): `plan_cockpit_sync.py` counted only
  `status == "done"`, while FleetPlan's canonical terminal value is `completed`. T-202 was
  `completed`, so the published mission surface said **6/9** and rendered T-202 as ⏳ pending while
  PLAN.md had it `[x]`.
- Fix: `_is_task_done()` accepting both spellings (canonical `completed`, legacy `done`) at the four
  counting/rendering sites; regression test `test_plan_yaml_counts_completed_as_terminal`.
- Evidence: focused `15 passed`; full suite `1435 passed / 1 skipped`; collector now reports **7/9**.
- The other three audit mismatches: G1/wave attribution fixed in PLAN.md (gate belongs to the wave it
  unblocks, matching G2); the un-IDed "lanes externas" bullet became a plain bullet so it stops
  inflating the `pd validate` task count; the `done`/`completed` vocabulary split is now covered by
  code, not by convention.

## Closeout audit — gaps carried into T-401 (02/11)

All nine claims in PLAN/CONTEXT reproduced on `main` (pytest 1434/1 skipped at the time, `pd validate`
10/11, determinism with both timestamps popped, live `hermes:desktop` = `stale` because the bus event
is 24 days old, `docs/ACTIVITY-EVENTS.md` linked, ruff 21 pre-existing / 0 new on the touched files).

- **`pd validate --deep` does not validate `plan.yaml` at all** — the 11 checks cover SPEC/PLAN/
  CONTEXT/STATE/VERIFICATION/tests. The only machine check is the FleetPlan dogfood load, which is why
  a status-token drift could live for weeks. T-401 must run the dogfood load and say so.
- All five SPEC success-criteria checkboxes are still `- [ ]`; four are evidenced by now (swarm
  surface, activity contract, Hermes emitter, steering contract). The fifth is `pd validate` green +
  `VERIFICATION.md`, which is T-401's own deliverable — it can only be ticked at the end.
- `docs/PLAN-COCKPIT.md` references `docs/ACTIVITY-EVENTS.md` as a code path under `## Related`
  rather than a markdown link (NIT, cosmetic).
- `STATE.json` `phase: 0 / status: initialized` with an empty `fleet_state` is the house norm for
  closed missions in this repo (plan-cockpit-v1 and b15b-gateway look identical) — not a defect.

## Post-G3 — manifest check no CLI (02/11)

- `pd validate --deep` ganhou um 12º check: o `plan.yaml` precisa carregar no modelo `FleetPlan`, todo
  status de task/wave precisa estar em `LifecycleState` e toda referência task→wave / wave→task /
  wave→gate precisa resolver. Era o buraco que deixou o drift de `done` viver semanas.
- Os três manifestos do repo foram migrados de `done` para `completed` (45 linhas). `done` não existe
  no enum, e é por isso que `pd fleet-run` recusava checkpoint com esse status.
- Efeito colateral declarado: `b15b-gateway` e `plan-cockpit-v1` passam a marcar 11/12 (falham só em
  `Test files`), onde antes marcavam 11/11 — o denominador mudou porque o check passou a existir.

