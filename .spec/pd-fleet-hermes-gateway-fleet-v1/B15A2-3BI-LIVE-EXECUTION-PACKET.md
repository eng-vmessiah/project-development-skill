# B15a.2 3b-i — Live Execution Packet (update do runtime vivo + patches do seam)

**Status:** aguardando aprovação do Vitor. **3b-ii (ativar o fleet) fica FORA** — este packet deixa tudo dormente/default-off.
**Objetivo:** runtime vivo na base verificada `ea81748579` + os 21 patches do seam aplicados (default-off) + restart controlado + smoke — pré-requisito do "fleet no ar".

## Alvos (verificados 04/10)

- **Checkout:** `~/.hermes/hermes-agent` — branch `main` (tracking `origin/main`, **behind 262**), tree limpo; `ea81748579` já disponível localmente.
- **Serviços** (systemd --user; ambos do mesmo checkout/venv):
  - `hermes-serve.service` — pid 1017034; `ExecStart=.venv-canary/bin/hermes serve --host 127.0.0.1 --port 9119 --skip-build`; `HERMES_HOME=~/.hermes`; `EnvironmentFile=~/.hermes/.env`; `Restart=always`.
  - `isis-gateway.service` — pid 970532; `hermes gateway run --replace --accept-hooks`; cwd `~/project/isis`; `RestartPreventExitStatus=78`; `TimeoutStopSec=240`.
- **`hermes update --plan` (read-only, já rodado):** confirma 2 serviços a reiniciar — gateway via `systemctl restart` (drain-first SIGUSR1) e serve "stop before code swap". *Output anexo abaixo.*
- **Deps:** `uv 0.11.7` no PATH; `uv.lock` presente; venv alvo `UV_PROJECT_ENVIRONMENT=.venv-canary`.
- **DB:** `~/.hermes/state.db` (**1.3 GB** + WAL). O gap contém mudanças de schema de estado (`hermes_state_schema.py`, +48/−17) → **backup obrigatório antes**.

## Procedimento (executor: ISIS na janela; Vitor acompanha)

1. **Stop:** `systemctl --user stop hermes-serve isis-gateway` (Desktop desconecta; bots param).
2. **Backup:** `~/backups/b15a2-3bi-<ts>/` ← `state.db`, `state.db-wal`, `state.db-shm` + `git rev-parse HEAD` + `git status` + `systemctl --user cat` dos 2 units.
3. **Update (usa rede):** `cd ~/.hermes/hermes-agent && git fetch origin && git merge --ff-only ea81748579` (pin exato — sem drift se `origin/main` avançar depois).
4. **Deps:** `UV_PROJECT_ENVIRONMENT=.venv-canary uv sync --frozen` (fallback `uv sync` se o lock reportar desatualizado).
5. **Patches:** `git am ~/project/project-development-skill/patches/b15a2-live/*.patch` (21; mesma base → aplicação limpa esperada; **`git am --abort` + parar em qualquer problema**).
6. **Verify (antes de subir):** `git log --oneline -22`; tree limpo; import check:
   `cd ~/.hermes/hermes-agent && HERMES_HOME=~/.hermes .venv-canary/bin/python -c "import tui_gateway.server, hermes_cli.fleet_tui_session; print('import ok')"`.
7. **Start:** `systemctl --user start hermes-serve isis-gateway`.
8. **Smoke:** ambos `active (running)`; serve responde em `127.0.0.1:9119`; **Desktop reconecta** (check visual); uma sessão de teste funciona; gateway sem `EX_CONFIG`/exit 78 nos logs; `hermes plugins list` ainda mostra `pd-fleet-hermes · not enabled` (default-off intacto).
9. **Confirmação de default-off:** o seam fica **dormente** (nenhum call site ativa o fleet runtime) — comportamento idêntico ao pré-update + 262 commits de upstream.

## Rollback

- **N1 (só os patches):** stop → `git reset --hard ea81748579` → start.
- **N2 (update inteiro):** stop → `git reset --hard 44533f11e3` → **restore do `state.db` do backup** (se o boot novo já migrou o schema) → start.
- **N3 (deps quebradas):** `git reset --hard 44533f11e3` + `UV_PROJECT_ENVIRONMENT=.venv-canary uv sync` no lock antigo.

## Stop criteria

Falha em qualquer passo 3–6 (fetch/merge/uv/am/import) → **não subir**, rollback conforme, reportar. Pós-start: serviço não sobe, logs `EX_CONFIG`, Desktop não reconecta, ou qualquer comportamento anômalo → rollback + report.

## Janela & custos declarados

- **Downtime:** Desktop desconectado + bots (Discord/Telegram/WhatsApp) parados ~**10–20 min** (backup de 1.3 GB + fetch de 262 commits + uv sync + restart).
- **Rede:** apenas `git fetch origin` (GitHub). Sem credenciais novas; `.env` intocado.
- **Fora de escopo:** 3b-ii (ativar), qualquer enable, config, rede extra, B15b.

## Aprovação

- [ ] **Autorizar 3b-i** — executar o procedimento acima na janela combinada.
- [ ] Vitor presente na janela? (horário: ____)

## Anexo — `hermes update --plan` (04/10, read-only)

```
Update plan:
  Install: git (v0.21.5 @ 44533f11)
  Profiles: default, coding, discord
  Running services to restart (2):
    • gateway [default] pid 970532 — systemd @ 44533f11
      restart: systemctl restart (drain-first SIGUSR1 when supported)
    • serve [default] pid 1017034 — manual-serve
      restart: stop before code swap, relaunch with recorded launch args
```

*Nota: o classificador do plano rotula o serve como "manual-serve"; na prática é `hermes-serve.service` (systemd --user) — o procedimento acima usa `systemctl --user` explicitamente. Após o 3b-i, updates futuros podem usar o caminho canônico `hermes update` normalmente.*
