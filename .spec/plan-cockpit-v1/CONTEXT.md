# CONTEXT.md — plan-cockpit-v1

## Decisions

- 2026-10-04 · Scope A+B (owner: Vitor): collector + Mission Control + pd feeding + real fleet pilot.
- 2026-10-04 · **G1 APPROVED** (owner, after SPEC review). Waves 1+ unblocked. Automation clarified: refresh scheduled (T-203) + fleet self-records; transitions = skill-enforced habit.
- 2026-10-04 · **T-203 cron CREATED (owner-approved)**: "plan-cockpit-refresh" every 30m — no_agent script `plan_cockpit_publish.sh` (silent on success; deliver local). Trigger points: cron + manual `--publish` at PD checkpoints.
- 2026-10-04 · Dashboard `file` bindings located: `~/.hermes/boardstate-state/dashboard/data/` (no cache; `.md`/`.csv` raw, JSON + pointer). mc tab widgets switched to live file bindings; `--widgets`/mc-widgets.json kept for rebuilds after app workspace resets.
- 2026-10-04 · **T-204 added** (owner asked "escolher a missão no painel?"): action-form selector → agent re-publishes `mc/mission.json` + "Plano da missão" widget (real waves/tasks/gates per mission).
- 2026-10-04 · Branch `feat/plan-cockpit-v1`, base `c526b27` (tip of `feat/b15a2-host-integration`); no worktree (focused feature on the repo itself).
- 2026-10-04 · `plan-cockpit.json` is ALWAYS derived (never hand-authored); legacy features labeled `source: state-md`; no backfill.
- 2026-10-04 · Pilot uses the EXISTING real runtime template (`hermes chat -q … --safe-mode --max-turns 1`) with pinned provider/model; outputs to an explicit dir; G2 authorization before live dispatch.

## Trade-offs

- Repo-local script (not a new `pd` subcommand) in v1 — less Core surface; promotion to `pd cockpit-export` deferred to v2.
- Static bindings (pd-studio pattern) in v1; rpc/file bindings when the dashboard data dir is located.

## Notes

- Real machinery that already exists: FleetPlan v1/v2 (`scripts/pd_fleet/models.py`), `examples/pd-fleet/run_local.py` (simulated e2e), runtime adapters (`scripts/pd_fleet/runtime_adapters.py` — templates: hermes / codex-cli / opencode / claude-code; status "Hermes integration pending"), supervisor / run_store / checkpoints / handoff.
- Golden rule: never fabricate telemetry.
- `pd` state semantics: `STATE.json.tasks` = completed-task strings (legacy); structured plan state lives in `fleet_state` + FleetPlan manifests.
- Executor question is ANSWERED by the machinery: runtime adapters dispatch via templated CLI commands with pinned provider/model — the pilot just wires/uses it.
