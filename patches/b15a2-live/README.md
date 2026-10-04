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

## Regenerar esta série

```
cd ~/project/hermes-agent-b15a2-integration
git format-patch --no-signature -o /tmp/p1 ea81748579..e98c30490b   # seam (4)
git format-patch --no-signature -o /tmp/p2 ea81748579..d501af7a68   # observer (10)
git format-patch --no-signature -o /tmp/p3 63301027cc..df97ad1a87   # S1–S6+F2 (7)
# concatenar em ordem 0001..0021
```
