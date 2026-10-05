# PILOT-PLAN — wave 4 real dispatch pilot (T-402)

## Scope

- **Plan:** `examples/pd-fleet/plan.yaml` (3 tasks — each writes one small artifact into the output dir).
- **Executor:** the REAL runtime adapter `hermes/openai-codex` via `hermes chat -q` one-shots
  (`--provider openai-codex --model <pinned> -Q --safe-mode --ignore-rules --max-turns 1`).
- **Runner:** `scripts/pd_fleet/run_hermes_pilot.py --live --authorized`
  (thin runner on top of the existing Fleet classes; smoke verified in T-401).

## Caps (declared)

- **Model pinned:** `deepseek-v4.1-flash` (provider `opencode-go`) — cheapest configured; 1 turn/task.
- **Invocations:** exactly **3** (one per task); per-task timeout 120s; 64KiB output caps.
- **Output dir:** `.spec/pilot-runs/hermes/` — nothing written outside it; sandbox allowlist =
  the exact argv tuples; executable pinned (`/home/vitor/.local/bin/hermes` in trusted_executables).
- **Estimated cost:** 3 flash calls × 1 turn × prompts ≤300 chars → **a few cents (< US$0.10)**.

## Safety

- `dispatch: live` opens ONLY for this one run (G2); `--authorized` flag is mandatory.
- No new credentials (uses the existing hermes config); no external effects beyond the output dir.
- Rollback: delete `.spec/pilot-runs/hermes/` — nothing else persists.

## G2 checklist (owner)

- [x] **Authorize the live run** — G2 APPROVED by owner (04/10, "autorizado").
- [ ] After the run: reports/evidence/summary in the output dir; the cockpit shows the run
  (T-403 evidence + T-404 review).
