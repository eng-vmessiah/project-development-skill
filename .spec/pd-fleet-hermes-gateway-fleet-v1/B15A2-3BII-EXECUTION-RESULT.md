# B15a.2 3b-ii — Execution Result (ativação, 04/10/2026)

**Status: ✅ EXECUTED — fleet TUI canary LIGADO no serve vivo; observação real via wire; aba Fleet no Board.**

## O que rodou

- Script `run-3bii.sh` (backup dir `~/backups/b15a2-3bii-20261004-2238/`), executado pelo operador às 22:41:
  stop → `git am` do patch **0022** → drop-in systemd (`HERMES_FLEET_TUI_CANARY=1` **só** no `hermes-serve`)
  → daemon-reload → start → smoke.
- Smoke: journal do serve às 22:41:53 → **`[fleet-canary] enabled: fleet.session.activate, fleet.session.status, fleet.session.deactivate, fleet.session.replay`**.
- Live tip: `dc50153faf` (0022 sobre `6b5d888382`); tree limpo; serviços de pé (serve pid 1534474, HTTP ok).

## Observação real (via `/api/ws` :9119, loopback + token)

`scripts/fleet_studio_sync.py` (PD) — RPC ao vivo `fleet.session.*`, token lido de `~/.hermes/.env` (nunca impresso):

- **activate** → `assoc.6df294d9c61d8d4c` · **status** → **`state: observing`** (epoch `c5b68788fdd64fcd89778890ed494a54`, boundary `bnd.c5b68788fdd6.3`, sequence 3).
- **Eventos REAIS capturados no wire** (ciclo `deactivate → activate → replay(cursor antigo)`):
  - `session.detached` — seq 2, `reason_code: user_deactivate`
  - `session.registered` — seq 3, `status: observing`
- Refresh validado: replay do cursor persistido → `events: []` + cursor avança (sem eventos novos).

## Aba Fleet (Board)

- Nova aba **“Fleet — B15a.2 (canary local)”** (workspace v30): Overview + Estado da associação + **Eventos observados (reais do wire)** + Fontes/Regras/Limitações.
- Refresh: `python3 scripts/fleet_studio_sync.py` → reaplicar bindings (padrão pd-studio).

## Limitações registradas (honestas)

- `status`/`heartbeat` não alimentados (decisão de semântica **D4 pendente**) — o fluxo contínuo do wire é vazio por design.
- `ended`/`detached` encerram a associação; o ciclo de captura expõe `detached`+`registered` (o `ended` da sessão fechada não é replayável pós-teardown — limitação S6).
- Canário resolve **exatamente 1 sessão viva** (0/ambíguo → fail-closed); identidade é server-side (o wire não expõe session ref).
- Readiness LIVE completa segue **`NOT_READY_HERMES_SEAM`** (G4 §10 aberto) — este é o canário local autorizado.

## Rollback

- **R1** (fleet off, código fica): `rm ~/.config/systemd/user/hermes-serve.service.d/fleet-canary.conf` + `systemctl --user daemon-reload` + `systemctl --user restart hermes-serve`.
- **R2** (reverter código): R1 + `git -C ~/.hermes/hermes-agent reset --hard 6b5d888382` + restart.

## Evidências

- `~/backups/b15a2-3bii-20261004-2238/run.log` (execução completa)
- `.spec/pd-studio/fleet-snapshot.json` (captura integral do wire)
- Board: aba Fleet (workspace v30)
- Árvore: boot tests 4✓ · grupo fleet 77✓ · lifespan sanity 39✓ · ruff ✓ · **canônica `tests/tui_gateway`: 93 falhas / 24 arquivos — conjunto idêntico ao baseline** (flake `change_watcher_sessions` passou nesta rodada; collection error `ephemeral_profile_override` = pré-existente) → **delta zero**.
