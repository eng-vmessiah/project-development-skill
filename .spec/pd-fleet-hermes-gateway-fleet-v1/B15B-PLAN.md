# B15B — Gateway de mensagens/API (draft plan v0.3)

**Status:** `draft_v0_3_reviewed` — B15b **não iniciado**; o canário TUI B15a.2 **segue live e autorizado** (desde 04/10 22:41, drop-in `HERMES_FLEET_TUI_CANARY=1`); live readiness do Fleet segue `NOT_READY_HERMES_SEAM`.
**Data:** 2026-10-05 · **Autoria:** ISIS (orchestrator) · **Aprovação do owner (Vitor):** pendente · **Review independente:** v0.1 → `PASS_WITH_BLOCKERS`; v0.2 → **`PASS`** (sem BLOCKER/HIGH — gate atendido); v0.3 = v0.2 + L2 residual + 2 NITs aplicados.
**Base documental:** `G1-CONTRACT.md` · `G4-AUTH-LIFECYCLE.md` (§10) · `G4-CLOSURE.md` (§1–3, §7–8) · `G4-SECURITY.md` · `B15-TUI-SEAM.md` (§B15b · não-objetivos · risco) · `B15A-EXECUTION-PLANS.md` (§B15b · planning gates · reconciliation) · `transport-wave-parked.md` (§4).

## 1. Escopo

B15b cobre (fonte: `B15A-EXECUTION-PLANS.md` §B15b + `B15-TUI-SEAM.md`):

- caller autenticado de **Discord/Telegram/API**;
- registration/activation por usuário e sessão;
- subscription **global ou escopo multi-sessão** (v1 propõe associação explícita; global/multi-sessão = deferimento proposto para v2 — ver §4/B15b.3);
- transporte autenticado e **associação durable**;
- **replay/rollback operacional** no processo `isis-gateway.service`.

Alvo de integração: `isis-gateway.service` (`hermes gateway run --replace --accept-hooks`, checkout vivo; canais Discord/Telegram/WhatsApp). Rollback operacional = stop→verify→start do serviço (procedimento detalhado em B15b.4).

Contrato base já desenhado no G1: vocabulário `fleet.connect` / `fleet.subscribe` / `fleet.disconnect`; envelope `pd-fleet-gateway-bridge:v1` (IDs opacos e limitados; redaction antes de persistência/entrega; `event_origin` = `gateway_native` vs `fleet_reconciled`); capability matrix v1 = **observation-only**; `fleet.subscribe` escopado a associação explícita (**sem wildcard em v1**).

## 1.1 Dependências (precondições)

- **Somente depois de B15a aprovado localmente** (`B15-TUI-SEAM.md` §B15b). Estado atual: B15a fases 1–3 executadas; **canário local LIVE** (autorizado; 3b-i/3b-ii + canônica com delta zero); readiness live completa segue `NOT_READY_HERMES_SEAM`.
- Corpus G1–G4 localmente verificado com doubles fake/injected — nunca substitui seam Hermes nem live.

## 2. Não-objetivos (explícitos, herdados + consolidados)

- Não transformar a TUI em Fleet global; não tratar a TUI como solução do caminho Discord/Telegram.
- Não reutilizar o canal de dashboard como descoberta global.
- Não habilitar `pd_fleet_gateway_enabled` em produção.
- Não expor o ticket ao TypeScript ou a endpoint público.
- Não conectar automaticamente a TUI ao `isis-gateway.service`.
- Sem wildcard subscription em v1; sem dispatch/mutação de sessão (observation-only v1).
- Transporte HTTP/SSE permanece **parked** até cumprir o redesign de 10 pontos (`transport-wave-parked.md` §4).

## 3. Decisões G4 §10 — propostas (draft; requerem aprovação owner/security; NÃO normativas)

| # | Decisão | Proposta | Conta |
|---|---|---|---|
| 1 | Transport auth concreto | Direção já aprovada = **Option B** (ticket one-use emitido pelo Gateway; mecanismo aberto). Proposta: identidade do caller resolvida **server-side** por canal (Discord/Telegram = identidade do adapter; API = **boundary** de token de sessão reaproveitado apenas como boundary de autenticação — mantendo as decisões registradas: API key global **não** é identidade Fleet; `TokenPrincipal` **não** é identidade humana; binding owner/profile/workspace é **Hermes-owned**, verificado server-side). Nonce one-use ≥128-bit (candidato G4-CLOSURE §2); nunca claims do caller. | Hermes Gateway owner + security |
| 2 | Ticket issuance/consume API | Capability **internal-only** no processo gateway (Python); sem rota HTTP até os gates do parked; emissão vinculada a principal autenticado + associação. | Hermes Gateway owner |
| 3 | Storage autoritativo + boundary atômico | Transação **single-writer** no state store do gateway (`hermes_state_gateway.py`); consume+association commit atômicos (regras locais G4 §4 como base). | Hermes Gateway owner |
| 4 | TTLs/clock-skew/cleanup/tombstone | Adotar candidatos do `G4-CLOSURE` §2 como normativos propostos (5min/90s/30s/15min/60s/4KiB/8KiB/100) + **novos**: clock-skew ±30s; tombstone de nonce ≥ TTL ativo + skew; retenção de tombstone 24h. | PD Fleet owner + security |
| 5 | Revogação: fonte + latência | Revogação via deactivation/control-plane do gateway; propagação ≤ 1 heartbeat (30s); fail-closed em estado stale/desconhecido. | PD Fleet owner + PD Core governance owner (mecanismo Gateway-side — G4-AUTH-LIFECYCLE §7; alinhado ao G4-SECURITY §8) |
| 6 | Retry idempotente | Mesma idempotency key ⇒ mesmo resultado terminal; reuso conflitante ⇒ deny (carregar semântica local G4 §5 para o seam vivo). | PD Fleet owner |
| 7 | Security review + fixtures live | Adaptar a matriz G4 §9 do `B15A2-EVIDENCE-PACKET` ao gateway real; executar **somente** em slice live separadamente autorizado; buckets reportados separados (contract/fake/TUI/seam/live). | security reviewer |
| 8 | Rotação de chave/token (G4-CLOSURE §3/§7) | Mecanismo Hermes-owned com grace window; verificação aceita N e N-1 durante rotação; congelar no B15b.0. | Hermes Gateway owner + security |
| 9 | Sequence persistence + retention (G4-CLOSURE §7) | Persistência no store do gateway; retenção ≥ cursor TTL + tombstones; congelar no B15b.0 (dependente de G3). | Hermes Gateway owner + PD Fleet owner |
| 10 | Cursor epoch/restart recovery (G4-CLOSURE §7) | Epoch novo por restart; gap **explícito** (`replay_gap`/`cursor_stale` — taxonomia G1 §7; `resync_required` só quando snapshot/boundary não comprovável), nunca silencioso; congelar no B15b.0. | Hermes Gateway owner + PD Fleet owner |
| 11 | Allowlist/denylist de redação (G4-CLOSURE §7) | Allowlist metadata-only conforme `G4-SECURITY` §5; fixtures nomeadas por campo; aprovação security antes de B15b.2. | security reviewer |

### 3.1 Blockers de reconciliação B15a→B15b (disposição explícita)

Os 6 blockers do `B15A-EXECUTION-PLANS.md` (Reconciliation) permanecem portões de design; disposição no B15b:

1. **Hermes seam (contrato de registration/dispatch)** → B15b.1 especifica o contrato do seam (event publisher + principal resolution) ANTES de qualquer patch; sem contrato revisado, B15b.1 não inicia.
2. **Identidade (cadeia confiável conexão↔processo↔profile↔workspace↔sessão↔observer)** → B15b.0 congela a cadeia; B15b.2 implementa; deny-by-default em ambiguidade.
3. **Composite deny (all-gates-pass: plugin allow-list + flag + seam + caller + sessão + associação + capability + lifecycle; config malformada/hot-reload não amplia acesso)** → **entregável explícito do B15b.0** (matriz) + fixtures nomeadas em B15b.2 e B15b.5.
4. **Wire contract fechado (allow-lists, bounds byte/depth/cardinalidade, control-chars, normalização, redaction antes de buffer/persistência/replay/log/métrica/entrega)** → B15b.0 (freeze do schema) + evidência em B15b.2/.5.
5. **Delivery/recovery (snapshot-before-stream, boundary atômico, cursor issuer/binding, epoch restart, retention/tombstones, outbox/ack, heartbeat/TTL/grace, crash points)** → B15b.3 (ordering/TTL) + B15b.4 (epoch/restart/crash), com critérios de aceite.
6. **Naming (um vocabulário autoritativo; sem alias silencioso)** → B15b.0 (mapping TUI↔bridge), com a seleção do vocabulário autoritativo pelo **Hermes owner** (G1 §3).
7. **Lifecycle authority (G4-CLOSURE §8: reconnect, duplicate attach, session end, normal exit, crash, restart epoch, in-flight)** → state machine em B15b.2; crash/restart em B15b.4 (paridade com o §8 fechada).

## 4. Decomposição (fases + gates + critérios de saída)

- **B15b.0 — Contratos & decisões** (docs only, repo PD): fechar §3 (7+4 decisões); **matriz composite-deny** (§3.1.3); congelar wire vocabulary mapping (seleção pelo Hermes owner); decision matrix + review packet. **Saída:** review independente sem BLOCKER/HIGH + **aprovação do owner**. Sem tocar o checkout Hermes.
- **B15b.1 — Host seam read-only** (event publisher + resolução de principal; lazy/namespaced default-off, como o patch `0010` do B15a): série replayable em `patches/`. **Entrada:** autorização separada para editar o checkout Hermes. **Saída:** default-off/absent/disabled fixtures; golden non-Fleet; 0 call sites; série aplica limpo em cópia.
- **B15b.2 — Auth + associação**: issuance/consume internal-only, state machine (regras G4), store durável, idempotência; fixtures locais apenas (sem ativação). **Saída:** fixtures locais verdes (consume/associação/idempotência/composite-deny/redaction) + aprovação da allowlist (§3.11).
- **B15b.3 — Escopo de subscription**: associação explícita (v1); global/multi-sessão deferido (proposta); delivery/ack ordering + heartbeat/TTLs. **Saída:** fixtures de ordering/TTL/heartbeat; gap explícito.
- **B15b.4 — Replay/rollback operacional**: replay com epochs/boundaries; procedimento de rollback do `isis-gateway.service` (stop/verify/start); crash-point matrix. **Saída:** rollback ensaiado em ambiente controlado; crash points documentados.
- **B15b.5 — Validação live + closeout**: slice live **separadamente autorizado**; fixtures negativas; evidence packet com buckets separados; G4 live closure. **Saída:** evidência live com buckets separados; `local_verified` nunca substitui `NOT_READY_HERMES_SEAM`.

## 5. Autorizações necessárias (checklist do owner)

- [ ] Aprovar este plano (direção + decomposição).
- [ ] (B15b.1) Autorizar edição do checkout Hermes (série replayable, sem instalação).
- [ ] (pós-B15b.4) Autorizar instalação/ativação do pacote no checkout vivo.
- [ ] (B15b.5) Autorizar live validation (escopo + rollback + downtime declarados).
- [ ] (contínuo) Aprovações owner/security das decisões §3 conforme a tabela.

## 6. Riscos e limites herdados

- `gateway/` ≈ 63k linhas de `.py` de 1º nível (123 arquivos; pacote total ≈ 95,5k `.py`); o seam deve ser mínimo (publisher + principal resolution), lazy/namespaced, default-off, 0 call sites até ativação.
- Memória: observar Node/`tui_gateway`/workers/subprocessos antes de canary prolongado (incidente OOM do WSL não comprovado causal — mas observável).
- **Downtime dos bots:** o slice live (B15b.5) implica restart do `isis-gateway.service` → Discord/Telegram/WhatsApp fora ~10–20 min (mesmo padrão declarado no 3b-i); mitigação/rollback no B15b.4.
- Readiness live permanece `NOT_READY_HERMES_SEAM` até: decisões implementadas + review + autorização separada + validação.
- Redaction antes de qualquer buffer/persistência/replay/log/métrica/entrega (G4-SECURITY).

## 7. Próximos passos

1. **Re-review focado** da v0.2 (B1/H1/M1–M5/L1–L7) — a dispatchar.
2. **Aprovação do owner** (Vitor) sobre a direção.
3. B15b.0: decision matrix + composite-deny + wire vocabulary mapping congelados.
4. Feature cockpit-ready para trackear B15b (padrão plan-cockpit) + feedings no `pd`.
