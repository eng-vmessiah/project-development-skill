# B15a.2 3b-i — Execution Result (04/10/2026)

**Status: ✅ EXECUTED + VERIFIED — runtime on the series; fleet dormant (3b-ii pending).**

## O que rodou

Script `patches/b15a2-live/run-3bi.sh` (v1), executado pelo operador às 21:56:
stop → backup (state.db 1.3 GB) → fetch + ff-only `ea81748579` → uv sync →
`git am` 21/21 → verify. O check v1 (import) deu **falso-negativo** → `die()` restaurou
os serviços às 21:56:48; verificação profunda manual 22:0x–22:17.

## Falso-negativo do check v1 (lição)

O v1 checava `import tui_gateway.server` com `.venv-canary/bin/python` — que é um **shim**
(re-exec no python do PM, **sem** o venv gerenciado) → `ruamel` "ausente" ali (falso).
O env de runtime real = venv gerenciado do produto
(`~/.hermes/installs/4180fed3e6ab5465/environments/d66984ae3bcf4f5db7e14b4c6431eeb4/venv`),
resolvido via `/proc/<serve-pid>/maps`. Nada estava quebrado.

## Verificação (green)

| Item | Evidência |
|---|---|
| Update | repo @ `ea81748579` + 21 am-commits; tip `6b5d888382`; tree limpo |
| Serviços | serve (pid 1510299, HTTP 200) + gateway — ambos desde 21:56:48 |
| Env de runtime | fleet modules importam OK no venv gerenciado (check v2 validado ao vivo) |
| Plugin | `pd-fleet-hermes · not enabled · 0.1.0` (inalterado) |
| Fleet dormente | zero call sites de produção |
| `hermes doctor` | sem problemas de deps (7 issues pré-existentes) |

## Script v2

`run-3bi.sh` v2 (este diretório + `~/backups/b15a2-3bi-20261004-1835/`): check de import
movido para o smoke (pós-start), contra o venv de runtime via `/proc`; uv sync logado;
skip gracioso. **Usar v2 em re-execuções (N1/N2).** Rollback N1/N2 continua disponível
(packet + `POST-RUN-VERIFICATION.md` no backup dir).

## Próximo

**3b-ii** — ativar o fleet (`enable_fleet_tui_canary`) + "fleet no ar" + aba Fleet no Board.
Requer pedido explícito.
