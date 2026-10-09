# B15a.2 — Recuperação pós-update (08/10/2026) — HANDOFF

## O que aconteceu

O update 0.21.6 de 08/10 (19:30–19:37) resetou `~/.hermes/hermes-agent` para origin/main
(`9d05e7ff92`) e **largou a série local de 23 commits** (B15a.2 + B15b.1; tip antigo `966a079d`).
Efeito: o canário fleet TUI caiu do serve (código ausente do checkout; o env do drop-in
`fleet-canary.conf` segue setado, porém inerte). Nada foi perdido: ref de backup do update
(`refs/hermes-update-backups/diverged-main-20261008-223149-966a079d9c3d`, expira ~07/11) +
patches (`patches/b15a2-live/`) + worktrees.

## O que já foi feito (offline, sem tocar no vivo) — 08/10 noite

- Série **re-basada** em `recovery/b15a2-live-on-9d05e7f` (worktree `~/project/hermes-agent-replay-probe`):
  - `git am --3way` dos 22 patches (`patches/b15a2-live/0001–0022`) + B15b.1 (`0023`, exportado do ref).
  - **1 conflito** resolvido: `hermes_cli/plugins_manifest.py` (typing novo do upstream + campos do
    `integration_contract`; resolução = estrutura nova + adição do patch). Os outros 21 patches aplicaram limpos.
  - Equivalência com a série verificada de 04/10: **30/30 arquivos fora do overlap com diff byte-idêntico**
    no código (17) e nos testes (13); 7 arquivos de overlap com drift só de contexto (esperado).
  - **1 adaptação (0024):** teste de packaging usava `yaml` plano; upstream unificou YAML em `hermes_yaml` → `import hermes_yaml as yaml` (uvx ruff OK; commit --no-verify — lefthook sem ruff no PATH). `py_compile` OK (38 .py). **Testes:** 14 arquivos da série **235✓/0✗**; canônica base×recovery = **delta zero real** (30 falhas pré-existentes idênticas + flake conhecido `change_watcher*`); logs `tests-*.log`.
- **Pins:** base `9d05e7ff92d3edd9abdf20fe3d04551905cb995e` → tip `704f229a40b275275b7934083b7a219ad1c5b4b0` (24 commits = série + 0024 adaptação).

## Como ativar (janela do Vitor, ~1–2 min — derruba Desktop/bots)

```bash
bash ~/backups/b15a2-recovery-20261008/run-recovery-activate.sh --check   # pré-checagens read-only
bash ~/backups/b15a2-recovery-20261008/run-recovery-activate.sh           # executa
```

O script: stop serviços → `git merge --ff-only` → drop-in do canário (verifica/recria) → daemon-reload →
start → smoke (HTTP 200 + `[fleet-canary] enabled` no journal + import profundo no venv de runtime).
Falha no meio → restore automático (reset p/ a base + serviços de volta) + log em `run-activate.log`.

**Rollback manual:** R1 `rm ~/.config/systemd/user/hermes-serve.service.d/fleet-canary.conf` + daemon-reload +
restart serve (fleet off, código fica) · R2 = R1 + `git reset --hard 9d05e7ff92d3...` + restart.

**Depois de rodar:** chamar o agente no chat → pós-checagem (wire/aba Fleet) + registro nos docs.

## Re-geração / contexto

- Branch: `recovery/b15a2-live-on-9d05e7f` (no repo `~/.hermes/hermes-agent`; worktree em `~/project/hermes-agent-replay-probe`).
- Exports: `git -C ~/.hermes/hermes-agent format-patch --no-signature -o <dir> 9d05e7ff92d3...recovery/b15a2-live-on-9d05e7f`
- Base antiga/contexto: `patches/b15a2-live/README.md` · vault: `Projects/project-development-skill/b15a2-caminho.md` (bloco 08/10).

## ⚠️ Processo (não repetir o incidente)

Enquanto a série morar no checkout vivo, **update desse checkout = procedimento pinado (ff-only + replay),
NUNCA `hermes update` cru / botão "Update Hermes"** — senão o reset de divergência se repete a cada update.
