# VERIFICATION — plan-cockpit-v1 (closeout, T-501)

**Data:** 2026-10-05 · **Branch:** `feat/plan-cockpit-v1` · **Gate:** G3 (closeout, owner `orchestrator-isis`).

## Verified (evidence on disk)

| Item | Evidence |
|---|---|
| Coletor derivado-only `scripts/plan_cockpit_sync.py` | 14/14 tests; determinismo (2 runs idênticas exceto `generated_at`); snapshot real `.spec/pd-studio/plan-cockpit.json` |
| Aba `mc` ao vivo (8 widgets, file bindings) | `~/.hermes/boardstate-state/dashboard/data/mc/` (overview · fleet · tables · mission); validado via `boardstate_data_read` como um widget vê |
| Auto-refresh | cron `f9203296553a` (30m, `no_agent`, silencioso) + test-fire ok; próximo fire automático |
| Seletor de missão | troca real testada (plan-cockpit-v1 ↔ missão legada; aviso honesto p/ legadas) |
| Skill `plan-cockpit` | publicada (v1.1.0 no closeout); desc ≤60; lint ok |
| **Piloto real (wave 4)** | `pilot-hermes-pd-fleet` **3/3 completed** — artefatos + `dispatch-log.jsonl` em `.spec/pilot-runs/hermes/`; sandbox com allowlist exata + executável pinado (**sem bypass** — verificado por review independente) |
| Review independente (T-404) | C1/C2/C4 verificados; 22/22 testes; **correção de narrativa aplicada** (4 runs / 9 dispatches reais; o "PATH_DENIED" inicial era falso) |
| Testes | runner 8/8 · coletor 14/14 · ruff clean |

## Deferred (honest, not blocking)

- Persistência FleetRunStore para os runs do piloto (caminho V1 sem store) — evidência = `summary.json` + `dispatch-log.jsonl` + artefatos.
- Acceptance proxy = runtime-exit-ok (conteúdo revisado no T-404; validação automática de conteúdo fica p/ v2).
- Migração dos widgets das abas antigas (`pds`/`fleet`) para file bindings.
- Promoção do coletor a subcomando `pd cockpit-export` (v2).

## Blocked

- Nada bloqueado. O seam live completo do Hermes (G4 §10) permanece fora deste escopo (`NOT_READY_HERMES_SEAM`, tópico B15b separado).

## Records

- Diário `MEM-Diaria/2026/10/04.md` (23:20 → 00:40+) · vault `plan-cockpit.md` · `pd-studio.md` · `b15a2-caminho.md`.
- `pd`: `complete-task` para T-000…T-501 + checkpoints reais; `pd validate --deep` executado no closeout.
- Board: aba `mc` mostra **13/13 tasks** após o refresh final.
