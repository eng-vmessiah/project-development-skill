# B15a.2 Fase 3 — Runtime Readiness Packet (autorização requerida)

**Status:** 3a ✅ + 3b-prep ✅ executados (aprovados 04/10); 3b-i/ii aguardam pedido próprio.
**Base:** Fase 1 `LOCAL_SEAM_VERIFIED` + Fase 2 `canary local verificado` (Hermes `df97ad1a87`)
**Live readiness hoje:** `NOT_READY_HERMES_SEAM` — inalterado até esta autorização. Este packet não autoriza nada por si só.

## Contexto do runtime vivo (verificado 04/10)

- O **Hermes Desktop é cliente remoto**: `Hermes-WSL.cmd` → `HERMES_DESKTOP_REMOTE_URL=http://localhost:9119` → o gateway roda no **WSL**.
- Processo vivo: `hermes serve --host 127.0.0.1 --port 9119 --skip-build` (pid 1017034, desde 03/10 01:20), `sys.path=/home/vitor/.hermes/hermes-agent` — checkout **`44533f11e3`**, venv `.venv-canary`.
- Home do runtime: **`~/.hermes`** (WSL) — plugins ativos ali: boardstate, isis-cockpit, by2kb, grill-tab, worker-dashboard, needs-you, etc.
- O checkout vivo está **262 commits atrás** de `ea81748579` (o commit vivo `44533f11e3` é **ancestral** da base da série). Consequência: o caminho é **atualizar o vivo para `ea81748579` + aplicar a série** (não rebasear para trás) — ver 3b-i.

## Escopo 3a — instalação do plugin lifecycle-only (pedido)

| Item | Valor |
|---|---|
| **Alvo** | `~/.hermes/plugins/pd-fleet-hermes/` (home real WSL; o gateway vivo roda daqui) |
| **Artefato** | `plugins/pd-fleet-hermes/` do worktree Hermes `df97ad1a87` (bundled; `plugin.yaml` com `integration_contract: {namespace: pd-fleet, version: "1.0", default_enabled: false}`; hooks: `on_session_start`/`on_session_end`; zero tools/RPC) |
| **Fonte upstream** | PD repo `plugins/pd-fleet-hermes/` @ `824f000` (idêntico exceto o bloco `integration_contract` adicionado pelo packaging) |
| **Mudança de config** | **Nenhuma** — plugin entra **disabled** (`default_enabled: false`); sem allow-list nova |
| **Passos** | 1) copiar o dir → 2) `hermes plugins list` (processo CLI fresco) confirma discovery + disabled + contrato validado → 3) opcional: enable/rollback canary em profile de teste |
| **Operador** | Vitor (ou ISIS com autorização explícita na hora) |
| **Janela** | Quando o Vitor disser |
| **Rollback owner** | Vitor |
| **Stop criteria** | Manifest/hash divergente; erro de import/register; hooks além dos 2 declarados; qualquer tool/command/RPC/middleware/rede/provider/credencial/subprocesso/persistência; rollback não demonstrável |

**3a executado (04/10):** baseline ausente ✓ → artefato bundled (`df97ad1a87`) copiado e conferido idêntico → `hermes plugins list`: **`pd-fleet-hermes · not enabled · 0.1.0 · source user`** (JSON idem); contrato validado no pre-import (senão seria rejeitado). **Nenhum enable** (3a-canary não solicitado).

**Canary de enable (opcional, passo separado):** enable explícito SÓ em profile isolado de teste (ex.: `HERMES_HOME` temporário ou profile dedicado); provar: disabled baseline → enable → apenas os 2 hooks → sessão limpa → disable → processo fresco mostra disabled.

**Rollback 3a:** `hermes plugins disable pd-fleet-hermes` (se enabled) → remover `~/.hermes/plugins/pd-fleet-hermes/` → processo fresco confirma que não carrega.

## Escopo 3b — NÃO incluído (decisão separada, em duas etapas)

O "fleet no ar" de verdade (observação real das sessões TUI via `fleet.session.*` + aba Fleet do pd-studio) exige a série do seam no runtime vivo:

- **3b-prep ✅ (04/10):** série exportada replayable em `patches/b15a2-live/` (21 patches; base `ea81748579`); **replay provado** — `git am` em worktree limpo → 21/21 aplicados, tree **idêntico** a `df97ad1a87` (`git diff --quiet` vazio). README com procedimento e caveats.
- **3b-i (aplicar no runtime vivo) — pedido próprio:** atualizar `~/.hermes/hermes-agent` de `44533f11e3` → `ea81748579` (262 commits de upstream) + `git am` dos 21 patches (default-off; sem mudança de comportamento) + restart do `hermes serve` (janela do Vitor) + smoke. Rollback = revert dos patches/checkout + restart; **⚠️ backup do DB antes** (migrações de estado possíveis no primeiro boot do update).
- **3b-ii (ativar):** ligar o composition root (enable explícito), observação real + evento/aba Fleet. Requer sua decisão na hora, com janela e observação.

**Fora de escopo até nova autorização:** aplicar patches no runtime vivo, habilitar o fleet runtime, qualquer rede/credencial/provider, B15b.

## Preconditions (verificadas nesta preparação)

- Worktree integração limpo @ `df97ad1a87`; canônica `tests/tui_gateway`: **2350 passed / 94 failed** — delta vs pré-F2 = **apenas o flake pré-existente** `test_change_watcher_sessions.py` (falha intermitente ~50% mesmo isolado; comprovado falhando na base em 04/10); todos os demais arquivos idênticos.
- Fase 2: review independente owner/security — 1 major (TOCTOU) + 4 minors corrigidos; itens não-provados registrados no caminho.
- Plugin standalone: sem tools/RPC/middleware/comandos; contrato `pd-fleet 1.0`, `default_enabled: false` (validado pelo PluginManager no packaging, B15a.4).
- `~/.hermes/plugins/` tem 7 plugins ativos — esta instalação adiciona UM diretório, disabled.

## Acceptance (3a)

- Baseline: `pd-fleet-hermes` ausente/disabled.
- Pós-instalação: `hermes plugins list` mostra o plugin **disabled**, contrato validado; nenhuma superfície nova; nenhum hook dispara.
- (Se autorizado) canary de enable: apenas `on_session_start`/`on_session_end`; rollback em processo fresco = disabled.

## Aprovação solicitada (marque o que autoriza)

- [x] **3a** — ✅ executado 04/10: plugin `disabled` em `~/.hermes/plugins/pd-fleet-hermes/` + discovery confirmado.
- [ ] **3a-canary** — (opcional) enable/rollback em profile isolado de teste. *(não solicitado)*
- [x] **3b-prep** — ✅ executado 04/10: `patches/b15a2-live/` (21 patches, replay provado; tree idêntico).

**Não autorizado por este packet:** 3b-i (patches no runtime vivo) e 3b-ii (ativar) — exigirão pedido próprio quando o 3b-prep estiver pronto.
