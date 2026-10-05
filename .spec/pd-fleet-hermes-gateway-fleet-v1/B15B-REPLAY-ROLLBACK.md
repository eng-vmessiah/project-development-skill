# B15B — Replay/Rollback Operacional + Crash-Point Matrix (T-501, wave 5)

**Status:** `draft_v0_1` — entregável do T-501 (B15b.4). Rollback **ensaiado em ambiente controlado**; nenhuma ação no serviço vivo.
**Fonte:** `B15A-DELIVERY-RECOVERY-CONTRACT.md` (§Required crash invariants · §Replay and restart) · `B15B-DECISION-MATRIX.md` A9/A10 · `G1-CONTRACT.md` §7.

## 1. Procedimento de rollback — `isis-gateway.service` (referência)

Unit real (`~/.config/systemd/user/isis-gateway.service`): `Type=simple` · `Restart=on-failure` · `RestartSec=10` · `RestartPreventExitStatus=78` (park em EX_CONFIG — sem respawn-loop) · `TimeoutStopSec=240s` (drain do Hermes = 180s + margem).

**Stop → verify → start → verify:**
1. `systemctl --user stop isis-gateway` — aguarda o drain gracioso (até 240s).
2. **Verificar parado:** `systemctl --user is-active isis-gateway` → `inactive`; sem processo órfão.
3. `systemctl --user start isis-gateway`.
4. **Verificar saudável:** `is-active` → `active` + `MainPID` vivo + linha de boot do gateway.

**Execução no serviço vivo: SOMENTE o owner** — infra live; não é escopo deste T-501 (o ensaio é em ambiente controlado, §2).

## 2. Ensaio do rollback (ambiente controlado)

Script: `scripts/pd_fleet/rehearse_gateway_rollback.sh` — cria um unit **scratch** (`pd-gateway-rehearsal.service`, mesmo shape do real: `Type=simple`/`Restart=on-failure`) e executa o ciclo completo stop→verify→start→verify. **Guarda dura:** recusa operar `isis-gateway.service`. Cleanup automático (trap).

**Evidência (2026-10-05 17:56 UTC — exit 0):**
```text
[17:56:46] === rollback rehearsal (controlled) — unit=pd-gateway-rehearsal.service ===
[17:56:46] scratch unit installed
[17:56:47] start -> is-active: active
[17:56:47] stop -> is-active: inactive
[17:56:47] verify stopped: no active process
[17:56:48] restart -> is-active: active
[17:56:48] verify healthy: MainPID=1743931
[17:56:48] === REHEARSAL PASS (controlled environment; live isis-gateway untouched) ===
```

Gateway vivo verificado `active` **após** o ensaio (não tocado). Log bruto: `B15B-ROLLBACK-EVIDENCE.log`.

## 3. Crash-point matrix (contrato × cobertura local)

| # | Failure point (contrato) | Resultado exigido | Cobertura local | Status |
|---|---|---|---|---|
| 1 | before validation/redaction | no persist/outbox/cursor/ack | `validate_event` rejeita sem efeitos (fixtures de redaction); módulos não mutam | ✅ |
| 2 | after redaction before persist | cursor unchanged; safe reprocess | `append` gap/dup ⇒ `False` **sem mutação** (`test_gap_blocks_ingestion_cursor_advancement`) | ✅ |
| 3 | after event before outbox | reconstruct/retry idempotently | `read` re-registra no outbox com dedupe por sequence (`test_ack_flow_and_outbox_retry`) | ✅ |
| 4 | after outbox before cursor | dedupe then advance only after durability | cursor avança **só no ACK contíguo** (`test_ack_advances_only_contiguously`) | ✅ |
| 5 | after cursor before ACK | outbox retries; no loss | `pending()` retriável (`test_ack_flow_and_outbox_retry`) | ✅ |
| 6 | snapshot/boundary unavailable | `resync_required` | subscribe exige `boundary_ref`; gaps ⇒ `replay_gap`/`cursor_stale`/`cursor_expired` + `resync_required` | ✅ |
| 7 | continuity unknown after restart | no replay success; new epoch/resync/stale | epoch mismatch ⇒ `cursor_stale` (`test_cursor_stale_on_epoch_mismatch`); auth crash points §8 (`test_crash_before_consume_commit` / `test_crash_after_consume_before_response` / `test_restart_with_uncertain_consumption`) | ✅ |
| 8 | revoke racing cleanup | authoritative validation denies new replay | revoked ⇒ deny (`test_revoked_ticket`); detach cancela outbox (`test_detach_cancels_outbox_and_tombstones`) | ✅ |

## 4. Replay e epochs (A10)

- Epoch novo por restart; **gap explícito — nunca silencioso**: `cursor_stale` (epoch), `replay_gap` (retenção), `cursor_expired` (TTL) — com `resync_required` onde cabível (§3/§4 das fixtures de subscription).
- `resync_required` só quando snapshot/boundary não comprovável: subscribe devolve `None` sem `boundary_ref`; leitura com gap devolve instrução explícita.
- **Limite honesto:** este é o comportamento **local** (fixtures). Replay operacional contra o `isis-gateway.service` vivo é escopo do slice live (**B15b.5** — autorização separada; `local_verified` nunca substitui `NOT_READY_HERMES_SEAM`).

## 5. Não incluído (escopo live — B15b.5)

- Execução do procedimento §1 no serviço vivo (owner).
- Replay real pós-restart do gateway.
- Crash injection real (SIGKILL) — a matriz §3 é contrato + cobertura local.
