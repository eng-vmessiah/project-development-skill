# PILOT-PLAN — wave 4 real dispatch pilot (T-402)

## Scope

- **Plan:** `examples/pd-fleet/plan.yaml` (3 tasks — each writes one small artifact into the output dir).
- **Executor:** the REAL runtime adapter `hermes/opencode-go` via `hermes chat -q` one-shots
  (`--provider opencode-go --model deepseek-v4.1-flash -Q --safe-mode --ignore-rules --max-turns 8`).
- **Runner:** `scripts/pd_fleet/run_hermes_pilot.py --live --authorized`
  (thin runner on top of the existing Fleet classes; smoke verified in T-401).

## Caps (declared)

- **Model pinned:** `deepseek-v4.1-flash` (provider `opencode-go`) — cheapest configured; 1 turn/task.
- **Invocations (actual, amended after the T-404 review):** **9 dispatches** across 4 runs (2+2+2+3) —
  all real flash calls; per-task timeout 120s; 64KiB output caps.
- **Output dir:** `.spec/pilot-runs/hermes/` — nothing written outside it; sandbox allowlist =
  the exact argv tuples; executable pinned (`/home/vitor/.local/bin/hermes` in trusted_executables).
- **Cost (actual):** 9 dispatches (1–8 iterations each, flash model) → **cents (< US$0.10)**.
- **Amendment (04/10, corrected by the T-404 review):** the real failure of runs 1–2 was the
  **iteration budget** (`--max-turns 1` — agents read and never wrote; honest outputs recorded). An earlier
  "PATH_DENIED" diagnosis was **wrong** (the sandbox coerces `path_roots` to str at construction; the
  `str(output_root)` change is defensive only). What actually fixed it: `--max-turns` 1→4→**8** plus the
  **write-first** harness prompt (names the target file, "não leia arquivos") → 3/3 on run 4.

## Safety

- `dispatch: live` opens ONLY for this one run (G2); `--authorized` flag is mandatory.
- No new credentials (uses the existing hermes config); no external effects beyond the output dir.
- Rollback: delete `.spec/pilot-runs/hermes/` — nothing else persists.

## Known limits

- Acceptance proxy = runtime-exit-ok (artifact content reviewed separately; T-404).
- No FleetRunStore persistence (V1 orchestrator path) — evidence = `summary.json` + `dispatch-log.jsonl` + artifacts.
- The dispatch-log covers runs 2–4; run 1's dispatches are only in `~/.hermes/logs/agent.log`.

## G2 checklist (owner)

- [x] **Authorize the live run** — G2 APPROVED by owner (04/10, "autorizado").
- [ ] After the run: reports/evidence/summary in the output dir; the cockpit shows the run
  (T-403 evidence + T-404 review).
