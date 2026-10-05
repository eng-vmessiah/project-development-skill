# PLAN-COCKPIT — Mission Control over PD

The cockpit layer over PD: **plan → process machine → live visuals**. A mission's plan is
structured once; the collector derives state from real sources; the Board renders it with
live file bindings. Golden rule: **never fabricate telemetry** — no data → explicit empty.

## Cockpit-ready plan standard (per mission)

Every PD mission starts with the standard control plane (see the `pd` skill) PLUS a
machine plan at `.spec/<mission>/plan.yaml` (FleetPlan v1-compatible):

- `agents` (id/role), `waves` (id/tasks/status/gates),
- `tasks` (id/wave/role/objective/depends_on/allowed_paths/acceptance_criteria/
  validation_commands/blocked_when/retry_policy/owner/status),
- `gates` (id/kind/scope/owner/status/required_evidence).

Validate it with the repo's own models — `pd_fleet.models.FleetPlan.from_dict` (dogfood).
Human views: `PLAN.md` (checkboxes + `id · role · deps · paths · acceptance`), `CONTEXT.md`
(decisions/trade-offs), `STATE.md/json` (created by `pd init <mission>`). Dogfooded
reference: `.spec/plan-cockpit-v1/`.

## Feeding the pd (every transition, 1 command)

```bash
cd ~/project/project-development-skill
pd checkpoint -f <mission> --note "T-xxx done — evidence"   # gates/checkpoints
pd complete-task -f <mission> "T-xxx — what was delivered"   # task closed
pd advance -f <mission>                                       # phase change
pd validate --deep -f <mission>                               # structure check
```

Also flip the task's `status: done` in `plan.yaml` and `- [x]` in `PLAN.md` — the collector
reads those. Legacy missions (no plan.yaml) stay labeled `source: plan-md/state-md`; never
backfill fabricated history.

## Sync & publish (collector)

`scripts/plan_cockpit_sync.py` (run with `/usr/bin/python3`):

| Mode | Writes |
|---|---|
| (default) | prints the snapshot JSON |
| `--write` | `.spec/pd-studio/plan-cockpit.json` (repo aggregate) |
| `--widgets` | `.spec/pd-studio/mc-widgets.json` (rebuild payloads for the mc tab) |
| `--publish` | live files to `~/.hermes/boardstate-state/dashboard/data/mc/` (`overview.md`, `fleet.md`, `tables.json`, `mission.md`, `mission.json`) |
| `--mission NAME` | with `--publish`: selects the mission detail (persists across runs) |

Automatic refresh: cron `plan-cockpit-refresh` (every 30m, `no_agent`, silent, deliver
local) runs `~/.hermes/scripts/plan_cockpit_publish.sh` (`--publish` only — no repo churn).
Manual at PD checkpoints: `--write --widgets --publish`.

## Mission Control tab (`mc`)

Board tab "Mission Control — PD": Overview · Features · Tasks · Timeline · Fleet runs ·
Escolher missão (action-form selector) · Plano da missão (selecionada) · Tasks da missão
(selecionada). The last three read live `file` bindings (no cache — fresh data on load).

Selector flow: pick a mission in the form → the template message reaches the agent → run
`--publish --mission '<name>'` → the mission widgets update.

## Pitfalls

- `file` bindings resolve under `~/.hermes/boardstate-state/dashboard/data/` (≤1MB; `.md`/
  `.csv` raw; JSON + `pointer`); no cache on read.
- Tool-call static strings truncate at ~512 chars — keep widget values ≤500 and verify
  writes with `boardstate_workspace_get`.
- The app CAN reset the workspace; rebuild = re-create tabs + re-apply
  `.spec/pd-studio/mc-widgets.json`; keep workspace backups (`~/backups/boardstate-workspace-v*.json`).
- Table widgets: `bindings.rows` + `props.columns`; markdown: `bindings.content`; data in
  bindings, never props; boardstate `tool_call` items need the `name` field.
