# B15B — Live Validation Evidence (T-601)

**Status:** **executado** 2026-10-05 (G-3 aprovado pelo owner, "sim"). Janela declarada: 10–20 min · **downtime efetivo: ~3 s** (stop 15:08:40 → start 15:08:43) + boot (~1 min até subsistemas).
**Buckets separados** (contract · fake · TUI · seam · live) — `local_verified` **nunca** substitui `NOT_READY_HERMES_SEAM`.

## live

| Passo | Resultado |
|---|---|
| Preflight (read-only) | checkout vivo limpo @ `dc50153faf` (main) · serve MainPID=1534474 · gateway MainPID=1534475 · drop-in canário presente |
| Instalação (`git am`) | commit **`966a079d9c`** (rollback ref: `dc50153faf`) |
| Sanidade pós-install | `run_tests.sh tests/tui_gateway/test_plugin_observer.py` → **7/7 (100%)** |
| 0 call sites | `git grep` → apenas o arquivo de teste referencia o módulo |
| Restart (procedimento T-501) | stop rc=0 → `is-active` = `failed`* → start rc=0 → **active/running**, MainPID **1749556** |
| Downtime | **~3 s** (15:08:40→15:08:43) + boot (~1 min; logs de subsistemas às 15:09:34) |
| **default-off vivo** | probe no **env real do runtime** (`installs/…/venv` do serve): registry vazio; `publish`=0 (v1 e versão errada); registro sem flag ⇒ `PluginRpcRegistrationError` ✓ |
| `hermes-serve` | **intocado** — MainPID **1534474** (idêntico ao preflight) |
| Gateway saudável | active + processo vivo (`Ssl`) + boot logs (`gateway.log`: kanban dispatcher/cron scheduler; journal: warnings normais de skill_commands) |

\* **Quirk pré-existente documentado:** SIGTERM ⇒ o processo sai com exit 1 ⇒ o unit registra `failed` **após** o stop (stop rc=0); `start` recupera limpo. Já observado antes (nota 3b-i). Sem impacto funcional; rollback segue stop/start.

## seam

- Série `patches/b15b-seam/0001` aplicada no checkout vivo (mesma árvore verificada no replay: `39dd54e4be…`); fixtures **7/7 no checkout vivo**; **0 call sites** (inert por construção).

## TUI

- Canário B15a.2: drop-in `HERMES_FLEET_TUI_CANARY=1` presente; `hermes-serve` **não reiniciado** (MainPID estável) — comportamento preservado.

## fake / contract

- Suíte local `tests/fleet/` = **1351 passed / 0 errors** (camada fake/local: T-301/T-302/T-401 + anteriores).
- Contratos congelados: G1 · G4 · B15B (seam v0.3; bounds; allowlist G-2 aprovada).

## Rollback (pronto; não necessário)

```bash
git -C ~/.hermes/hermes-agent reset --hard dc50153faf
systemctl --user restart isis-gateway   # se preciso (procedimento ensaiado no T-501)
```

## Limites honestos

- Sem publisher/ativação de eventos (não existe — fases futuras); o seam é inert por construção.
- `NOT_READY_HERMES_SEAM` permanece o status de readiness live: este slice valida **instalação + default-off + estabilidade**, não o publisher live.
- Log bruto: `B15B-LIVE-EVIDENCE.log`.
