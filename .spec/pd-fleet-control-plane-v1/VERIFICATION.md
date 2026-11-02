# VERIFICATION.md — pd-fleet-control-plane-v1 (T-401)

Closed on **2026-11-02**. Every claim below was re-executed on this date against this repository;
none is inherited from a previous report. Where a number comes from a previous wave, the command to
reproduce it is given so the next reader can falsify it.

Split: **verified** (executed, with output) · **deferred** (deliberately out of v1, with the receiving
place) · **blocked** (external, not this mission's scope) · **not claimed** (things this mission never
promised).

---

## Verified

### R1 — activity event contract v1

| evidence | command | result |
|---|---|---|
| contract exists, 4 kinds, redaction, per-kind minimums | `sed -n '1,27p' .spec/pd-fleet-control-plane-v1/ACTIVITY-CONTRACT.md` | schema + `tool/file/status/heartbeat`, `v/event_id/ts/agent_id/run_id/source/fidelity/kind/action/paths/status/meta` |
| external doc required by R1 (`docs/`) | `ls -l docs/ACTIVITY-EVENTS.md` | 4177 bytes, linked from `docs/PLAN-COCKPIT.md` under `## Related` |
| fixtures parse and match the contract | `/usr/bin/python3 -m pytest tests/test_control_plane_swarm.py -q` | part of the suite below; contract guard in `.spec/pd-fleet-control-plane-v1/tests/` |

### R2 — read-only swarm surface (real sources, explicit empty)

| evidence | command | result |
|---|---|---|
| collector derives the namespace from real sources | `/usr/bin/python3 scripts/plan_cockpit_sync.py` | `swarm` block with 10 rows |
| published files exist and render | `ls -l ~/.hermes/boardstate-state/dashboard/data/swarm/` | `agents.md` 1502 B, `agents.json` 3104 B |
| missing source renders as explicit empty, never invented | `head -6 …/swarm/agents.md` | `kanban · status 'sem fonte' · hb —` next to real monitor rows |
| deterministic output | run twice, pop root `generated_at` **and** `swarm.generated_at`, sha1 the sorted JSON | `da8a8e28…e0f5` on both runs (equal) |

### R3 — Hermes-native activity source (local spike)

| evidence | command | result |
|---|---|---|
| emitter reads `state.db` read-only, writes a local redacted bus | `scripts/pd_fleet/activity_emit.py` + `~/.hermes/activity/events.jsonl` | 21 events on the bus; no network, no message content |
| idempotent re-run (watermark) | emitter `--dry-run` after a full pass | proposes 0 new events (watermark covers every `agent_id|run_id`) |
| staleness is honest at render time | `plan_cockpit_sync.py` (`STATUS_FRESH_S`) vs the 24-day-old bus event | live `hermes:desktop` renders `stale`, not `running` |
| window keyed on activity, not `ended_at` | T-202 review RISCO-3 test | `test_activity_emit_window_uses_activity_not_ended_at` |

### R4 — steering contract (design only, zero action surface)

| evidence | command | result |
|---|---|---|
| contract delivered | `wc -l .spec/pd-fleet-control-plane-v1/STEERING-CONTRACT.md` | 419 lines, 15 sections, D-006/D-007 declared |
| implementation boundary explicit | same file, §11 | seven preconditions for v2, label `designed, not implemented` |
| capability allowlist untouched | `steering/probes/run_probes.py` | `CAPABILITIES_V1=frozenset({'observation'})`; `steer.kill` → `denied_by=('B7',)` |
| effect-observation gap closed honestly | `probe_pause_semantics.py`, `probe_epoch_fencing.py` | `degraded/pause_not_observed`, `blocked/stale_owner_epoch` |
| reviewer from a different family | GLM-5.3-Flash via OpenCode CLI (read-only) | `PASS_WITH_RESERVATIONS` — 0 BLOCKER, 1 HIGH, 3 MEDIUM, 2 LOW, 1 NIT; all seven disposed (§15) |
| delta re-review on the workspace lane | Vigia (`Revisor PD`, GLM-5.3-Flash) on the Maestri canvas | `PASS` — 6/7 CLOSED, ST-06 CLOSED with wording reservation, 2 new NITs both fixed |
| grounding re-executable | `/usr/bin/python3 .spec/pd-fleet-control-plane-v1/steering/probes/run_probes.py` | `TOTAL=6 PASS=5 FAIL=1` — the FAIL is the **refuted** claim kept on purpose (runner accepts a URL in an allowlisted argv, so it is not a network boundary) |

### R5 — tests, no regressions, deterministic surfaces

| evidence | command | result |
|---|---|---|
| full suite | `/usr/bin/python3 -m pytest tests/ -q` | **1435 passed, 1 skipped** (8.9 s). The skip is `tests/fleet/test_b15a2_host_seam_harness.py:22` — `tui_gateway` not importable, pre-existing |
| new regression test for the panel bug | `pytest tests/test_plan_cockpit_sync.py -q` | **15 passed** (14 pre-existing + `test_plan_yaml_counts_completed_as_terminal`) |
| lint equal to baseline | `uvx ruff check` on the touched files vs `origin/main` | 6 pre-existing `UP017` in `plan_cockpit_sync.py` on both sides; **zero new** |
| structure check | `/usr/bin/python3 scripts/pd.py validate --deep -f pd-fleet-control-plane-v1` | **11/11** with this file present |

### R6 — records

| evidence | command | result |
|---|---|---|
| checkpoints | `ls .spec/pd-fleet-control-plane-v1/CHECKPOINT-*.md` + `STATE.json['checkpoints']` | 10 files, last `CHECKPOINT-20261102-1322.md`; `STATE.json` logs 11 entries (the first has no file — `pd init` counts the opening checkpoint twice, once as `created_at`) |
| vault | `~/isis-obsidian/Projects/project-development-skill/control-plane-workspace.md` | W1/W2/W3 sections + review chain recorded |
| roadmap cross-ref | `grep -n 'control-plane-v1' ROADMAP.md` | `ROADMAP.md:141` — "Tracked as `.spec/pd-fleet-control-plane-v1/` (opened 2026-10-09)" |
| state machine fed | `/usr/bin/python3 scripts/pd.py status` + collector | 10 tasks in `plan.yaml`, all terminal at closeout; 5 waves completed; G1/G2/G3 approved |

---

## Deferred (explicit, with the place it goes next)

1. **Steering implementation** (`steer/pause/resume/kill/retry` as code) — out of v1 by SPEC R4 and
   D-002. Requires its own mission with a blocking owner gate before the first T2 verb, a fake sink
   before any real sink, and an explicit `CAPABILITIES_V1` extension (§11.1–11.7 of the contract).
2. **R1 `kind:status` enum extension** (`paused`/`cancelling`/`cancelled`) — D-007. Until it exists, a
   pause/kill effect is proven by the sink's health snapshot, never by the bus.
3. **External-lane adapters** (agent-trail parser patterns, Kitchen-style role/todo observation for
   Codex/Claude lanes) — RESEARCH#6/#7, explicitly "reference input only". Lands with the next
   increment that opens external lanes; nothing is installed.
4. **Laya advisory wiring** — measured, not wired: sink 3/21 (14%), notify 15/21 (71% agreement at
   threshold 0.5), median ~262 ms, zero wire. Deferred until fine-tune/labels exist; the thresholds are
   a calibration task, not a config toggle (`spike-laya/RESULTS.md`, `decisions.jsonl`).
5. **`plan.yaml` is not covered by `pd validate --deep`** — the 11 checks never read the manifest, so a
   status-token drift can live for weeks (this is how the panel showed 6/9 while 7 tasks were done).
   Mitigation shipped in T-402 is a collector regression test; a manifest check belongs in the CLI.
6. **`docs/PLAN-COCKPIT.md` references `docs/ACTIVITY-EVENTS.md` as a path, not a markdown link** —
   cosmetic, found by the closeout audit.

## Blocked (external, not this mission's scope)

1. **Codex lane on the `T-301 steering` floor** — Maestri 0.28.2 refuses the recruit: *"Floor 'T-301
   steering' is a git-isolated floor with a local clone, but this manager uses a remote connection.
   The recruit would inherit that connection and couldn't reach the clone."* Fixed in 0.29.0, whose
   installer is downloaded and hash-verified but **not executed** (installing restarts the app and
   drops the three live terminals). The work was done without it: contract authored on the main lane,
   reviewed by two independent reviewers.
2. **Publishing** — 8 local commits on `main` are ready and unpublished. Repo rule: publish only on
   explicit owner approval. Nothing was forced or rebased.

## Not claimed

- No live dispatch, no provider activation, no network listener, no deployment.
- Zero action surface: `CAPABILITIES_V1 = {"observation"}` (probe-verified), board connector's
  allowlist unchanged (3 fixed sync scripts).
- `local_verified` never stands in for live readiness: this mission ships a **surface + contract**, not
  an executor.
