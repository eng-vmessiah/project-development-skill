# B15a.2 — Live patch series (base `ea81748579`)

21 patches replayable via `git am` para o seam do fleet TUI:

- **0001–0004** — seam (plugin RPC registry default-off, métodos segmentados, validação de `integration_contract`, batch atômico).
- **0005–0014** — série do observer (contrato desabilitado, transport, gate no api-server, activation owner, auth fail-closed, identidade dashboard, request bridge, tickets, wiring de lifecycle, fix bare-`__new__`).
- **0015–0021** — B15a.2 Fase 1 (S1–S6) + Fase 2 (codec D4, serviço, registro, hooks, refactor S5, fixes do S6, composition root do canário).

## Replay verificado (04/10)

- Worktree limpo em `ea81748579` + `git am patches/b15a2-live/*.patch` → **21/21 aplicados; tree IDÊNTICO a `df97ad1a87`** (`git diff --quiet` vazio).
- Evidência de testes nessa árvore: `B15A2-EVIDENCE-PACKET.md` + `b15a2-caminho.md` (grupo da sessão 224✓, canário 7✓, canônica `tests/tui_gateway` ≡ base).

## Gap do runtime vivo (fatos, 04/10)

- Checkout vivo: `~/.hermes/hermes-agent` @ `44533f11e3` (branch `main`; serve :9119, pid 1017034).
- `44533f11e3` é **ancestral** de `ea81748579`; o vivo está **262 commits atrás**.
- **Procedimento 3b-i** (requer autorização própria): atualizar o vivo para `ea81748579` (ou origin/main atual) → `git am` dos 21 patches → restart do `hermes serve` (janela do Vitor) → smoke (serve de pé, Desktop conecta).
- **Rollback**: `git revert`/reset dos 21 commits (ou checkout do commit anterior) + restart.
- **⚠️ Caveat**: o update upstream (262 commits) pode rodar migrações de estado no primeiro boot — **capturar backup do DB antes** do 3b-i.

## 3b-ii — ativação (patch 0022 + gate de boot) — 04/10

- **0022** — `tui_gateway/fleet_tui_boot.py` (gate explícito, default-off: só `HERMES_FLEET_TUI_CANARY=1` no ambiente do processo liga o composition root) + call site no `_lifespan` do `hermes_cli/web_server.py` (best-effort) + `tests/tui_gateway/test_fleet_tui_boot.py` (4 testes: no-op sem flag; enable idempotente; falha fail-soft; valores ≠ "1" = off). Aplicado com `git am` sobre o tip vivo `6b5d888382` — **`git apply --check` OK no checkout vivo (04/10 22:4x)**.
- **Ativação**: `run-3bii.sh` (backup dir `~/backups/b15a2-3bii-20261004-2238/` + esta pasta) — stop → `git am` 0022 → drop-in systemd `Environment=HERMES_FLEET_TUI_CANARY=1` **só no `hermes-serve`** → daemon-reload → start → smoke (`[fleet-canary] enabled` no journal).
- **Rollback**: **R1** (fleet off, código fica): `rm` do drop-in + daemon-reload + restart serve · **R2**: R1 + `git reset --hard 6b5d888382` + restart.
- **Evidências da árvore**: boot tests 4✓; grupo fleet 77✓; lifespan sanity 39✓; ruff ✓; canônica `tests/tui_gateway` em execução no fechamento (comparar com o baseline 93 falhas conhecidas).

## Regenerar esta série

```
cd ~/project/hermes-agent-b15a2-integration
git format-patch --no-signature -o /tmp/p1 ea81748579..e98c30490b   # seam (4)
git format-patch --no-signature -o /tmp/p2 ea81748579..d501af7a68   # observer (10)
git format-patch --no-signature -o /tmp/p3 63301027cc..df97ad1a87   # S1–S6+F2 (7)
# concatenar em ordem 0001..0021
```
