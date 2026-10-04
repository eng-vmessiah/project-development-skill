# B15a.2 Fase 3 — Runtime Readiness Packet (autorização requerida)

**Status:** `DRAFT — aguardando aprovação do Vitor (owner/operator)`
**Base:** Fase 1 `LOCAL_SEAM_VERIFIED` + Fase 2 `canary local verificado` (Hermes `df97ad1a87`)
**Live readiness hoje:** `NOT_READY_HERMES_SEAM` — inalterado até esta autorização. Este packet não autoriza nada por si só.

## Contexto do runtime vivo (verificado 04/10)

- O **Hermes Desktop é cliente remoto**: `Hermes-WSL.cmd` → `HERMES_DESKTOP_REMOTE_URL=http://localhost:9119` → o gateway roda no **WSL**.
- Processo vivo: `hermes serve --host 127.0.0.1 --port 9119 --skip-build` (pid 1017034, desde 03/10 01:20), `sys.path=/home/vitor/.hermes/hermes-agent` — checkout **`44533f11e3`**, venv `.venv-canary`.
- Home do runtime: **`~/.hermes`** (WSL) — plugins ativos ali: boardstate, isis-cockpit, by2kb, grill-tab, worker-dashboard, needs-you, etc.
- O worktree da Fase 1/2 (`hermes-agent-b15a2-integration`) é baseado em `ea81748579` (origin/main), **não** no commit vivo — a série precisa ser rebasada para `44533f11e3` antes de qualquer aplicação (ver 3b-prep).

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

**Canary de enable (opcional, passo separado):** enable explícito SÓ em profile isolado de teste (ex.: `HERMES_HOME` temporário ou profile dedicado); provar: disabled baseline → enable → apenas os 2 hooks → sessão limpa → disable → processo fresco mostra disabled.

**Rollback 3a:** `hermes plugins disable pd-fleet-hermes` (se enabled) → remover `~/.hermes/plugins/pd-fleet-hermes/` → processo fresco confirma que não carrega.

## Escopo 3b — NÃO incluído (decisão separada, em duas etapas)

O "fleet no ar" de verdade (observação real das sessões TUI via `fleet.session.*` + aba Fleet do pd-studio) exige a série do seam no runtime vivo:

- **3b-prep (local, sem tocar o runtime):** rebasear a série (S1–S6 + F2; hoje sobre `ea81748579`) para o commit vivo `44533f11e3`; exportar patch series replayable (substitui/estende `patches/0001–0010`, que são da geração pré-rebase); re-verificar canônica + suíte da sessão nessa base. **Este prep ainda é local e pode ser autorizado à parte.**
- **3b-i (aplicar no runtime vivo):** aplicar a série em `~/.hermes/hermes-agent` (default-off; nenhuma mudança de comportamento) + restart do `hermes serve` (por Vitor; janela combinada). Rollback = `git revert`/checkout dos patches + restart.
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

- [ ] **3a** — instalar `pd-fleet-hermes` (lifecycle-only, disabled) em `~/.hermes/plugins/` + discovery via `hermes plugins list`.
- [ ] **3a-canary** — (opcional) enable/rollback em profile isolado de teste.
- [ ] **3b-prep** — rebasear/exportar a série do seam para `44533f11e3` + re-verificação (ainda 100% local; não toca o runtime vivo).

**Não autorizado por este packet:** 3b-i (patches no runtime vivo) e 3b-ii (ativar) — exigirão pedido próprio quando o 3b-prep estiver pronto.
