# B15B — Decision Matrix (B15b.0)

**Status:** `b15b0_done` — propostas congeladas e assinadas (05/10). Review B15b.0: `PASS_WITH_BLOCKERS` → **`PASS`** (H1/M1/M2/L1–L3 resolvidos; N1–N3 aplicados). **G-0 FECHADO (05/10).** Nada implementado; canário TUI B15a.2 segue live e autorizado; readiness live do Fleet segue `NOT_READY_HERMES_SEAM`.
**Data:** 2026-10-05 · **Fonte:** `B15B-PLAN.md` v0.3 (§3 · §3.1 · §4) + corpus `G1-CONTRACT` / `G4-AUTH-LIFECYCLE` / `G4-CLOSURE` / `G4-SECURITY`.
**Aprovação:** ✅ owner + security + Hermes-owner cobertos (05/10, "autorizado"); pendências: nenhuma (review fechou; feeding completo).

## A. Decisões congeladas (11)

| # | Decisão | Resolução proposta (congelada) | Conta |
|---|---|---|---|
| A1 | Transport auth | Option B (direção aprovada): ticket one-use emitido pelo Gateway. Identidade do caller **server-side** por canal — Discord/Telegram: identidade do adapter; API: token de sessão apenas como **boundary** de autenticação (API key global **não** é identidade Fleet; `TokenPrincipal` **não** é identidade humana); binding owner/profile/workspace **Hermes-owned**. Nonce one-use ≥128-bit. Nunca claims do caller. | Hermes Gateway owner + security |
| A2 | Issuance/consume API | Capability **internal-only** no processo gateway (Python); sem rota HTTP até os gates do parked (10 pontos). Emissão vinculada a principal autenticado + associação. | Hermes Gateway owner |
| A3 | Storage + boundary atômico | Transação **single-writer** no state store do gateway (`hermes_state_gateway.py`); consume+association commit atômicos (base: regras locais G4 §4). | Hermes Gateway owner |
| A4 | TTLs/clock-skew/tombstone | Candidatos G4-CLOSURE §2 **propostos como normativos** (não embutir em runtime antes da aprovação — §2): 5min ativação · 90s idle · 30s heartbeat · 15min cursor · 60s grace · 4KiB payload · 8KiB envelope · 100 replay. **Novos:** clock-skew ±30s · tombstone ≥ TTL ativo + skew · retenção 24h. Bounds restantes (depth/Unicode/control/diagnostic/retry + fixtures nomeadas) congelados no contrato do seam (B15b.1). | PD Fleet owner + security |
| A5 | Revogação | Via deactivation/control-plane do gateway (mecanismo Gateway-side — G4-AUTH-LIFECYCLE §7); **proposta nova:** propagação ≤ 1 heartbeat (30s); fail-closed em estado stale/desconhecido. | PD Fleet owner + PD Core governance owner + security (revoke exige revisão Gateway/security — G4-CLOSURE §1; atribuição de fonte — G4-SECURITY §8) |
| A6 | Retry idempotente | Mesma idempotency key ⇒ mesmo resultado terminal; reuso conflitante ⇒ deny (semântica local G4 §5 carregada ao seam). | PD Fleet owner |
| A7 | Security review + fixtures live | Matriz G4 §9 (do `B15A2-EVIDENCE-PACKET`) adaptada ao gateway real; execução **somente** no slice live (B15b.5); buckets separados: contract / fake / TUI / seam / live. | security reviewer |
| A8 | Rotação de chave/token | Mecanismo Hermes-owned com grace window (**proposta nova:** verificação aceita N e N-1 durante rotação). | Hermes Gateway owner + security |
| A9 | Sequence persistence/retention | Persistência no store do gateway; retenção ≥ cursor TTL + tombstones (dependente de G3). | Hermes Gateway owner + PD Fleet owner |
| A10 | Cursor epoch/restart | Epoch novo por restart; gap **explícito** (`replay_gap`/`cursor_stale` — taxonomia G1 §7; `resync_required` só quando snapshot/boundary não comprovável); nunca silencioso. | Hermes Gateway owner + PD Fleet owner |
| A11 | Redaction allowlist/denylist | Allowlist metadata-only conforme G4-SECURITY §5; fixtures nomeadas por campo; aprovação security antes de B15b.2. | security reviewer |

**Mapeamento G4-CLOSURE §7 (11 linhas → disposição):** A8–A11 cobrem rotação / sequence-retention / cursor-epoch / redação; "atomic snapshot/boundary" e "cursor/outbox/ack ordering" têm disposição em `B15B-PLAN.md` §3.1.5 (B15b.3/.4); "approve durable ack ordering" = critério de saída de B15b.3; "approve cursor/activation verification" = A8 + B15b.2. **Demais linhas:** Option A/B/C = A1 (direção aprovada); heartbeat/TTL/grace/skew = A4; approve candidate bounds = A4 (sign-off formal ✅ 05/10); authorize G5 fixtures = A7 (local já autorizado; live no B15b.5). Sem linhas órfãs.

## B. Matriz composite-deny (all-gates-pass)

**Regra:** a capability de Fleet é concedida **somente** quando TODOS os gates abaixo passam. Qualquer gate ausente, malformado ou invalidado por hot-reload ⇒ **deny** (fail-closed), sem ampliação de acesso.

| # | Gate | Fonte do valor | Estado ausente/malformado | Efeito do deny |
|---|---|---|---|---|
| B1 | Plugin allow-list | config do plugin (Hermes) | ausente/inválido | sem registro de observer |
| B2 | Integration flag (`pd_fleet_gateway_enabled`) | config (default-off) | ausente/inválido | seam inativo |
| B3 | Seam suportado | contrato B15b.1 (versão compatível) | não suportado | sem event publisher |
| B4 | Caller autenticado | identidade server-side por canal | não autenticado | sem principal |
| B5 | Sessão ativa resolvida pelo servidor | server-resolved | ambígua/ausente | sem associação |
| B6 | Associação explícita | lifecycle (G4) | ausente | sem subscription |
| B7 | Capability allow-list | matrix v1 (observation-only) | fora da allow-list | sem dados |
| B8 | Lifecycle state atual | state machine (G4) | stale/revogado | sem entrega |

**Regras transversais:**
- Hot-reload que deixe configuração malformada **não amplia acesso** (re-validação a cada uso; config ruim ⇒ deny).
- Ambiguidade de identidade/sessão ⇒ deny (deny-by-default).
- Chamadas diretas ao dispatcher fora do funil ⇒ deny (defense-in-depth, padrão B15a).
- Nenhum gate é "herdado" de outra camada (ex.: auth de dashboard não satisfaz B4; TUI ativa não satisfaz B6).

## C. Wire vocabulary mapping (TUI ↔ bridge)

| Camada | Vocabulário | Significado | Autoridade |
|---|---|---|---|
| TUI control plane (B15a) | `fleet.session.activate` / `fleet.session.status` / `fleet.session.deactivate` / `fleet.session.replay` | operações locais na ÚNICA sessão TUI ativa | **D4 APROVADO** (02/08/2026 — Hermes/TUI owner); wire `pd-fleet-tui:v1` |
| Bridge transport (G1/B15b) | `fleet.connect` / `fleet.subscribe` / `fleet.disconnect` | ciclo de vida do observer no boundary do bridge | propostos (G1); **internos** até a seleção do Hermes owner (D4: bridge transport names are internal — MUST NOT be public aliases) |

**Regras de tradução (seleção coberta pelo owner — 05/10; G1 §3):**
- **Root compartilhado:** ambas as superfícies vivem sob o root `fleet.*` (`fleet.session.*` = TUI; `fleet.connect/subscribe/disconnect` = bridge). A política é de **registro sem colisão** sob o mesmo root (D1 rejeita colisões; nenhuma operação é servida por duas camadas) — não "prefixos distintos".
- **Um vocabulário autoritativo** (G1 §3): cada operação pertence a exatamente uma camada; nenhum alias silencioso entre camadas (nem `fleet.session.*`→bridge, nem o inverso).
- **Translation explícita:** uma associação TUI ativa pode ser a sessão referenciada por `fleet.subscribe` — via referência opaca da associação, nunca por reuso do comando; a tradução é documentada.
- **Authentication context:** por camada — TUI: caller local stdio/JSON-RPC (cadeia de identidade B15a); bridge: caller autenticado por canal (A1). O contexto de auth de uma camada NÃO satisfaz a outra (sem herança).
- **Error/version behavior:** taxonomias e versões por camada (bridge: G1 §7 + envelope `pd-fleet-gateway-bridge:v1`; TUI: wire `pd-fleet-tui:v1`); erros não cruzam camadas.
- **Default-off:** a seleção do vocabulário não habilita nada; ambas as camadas seguem default-off até autorização própria.

## D. Sign-off checklist (gate G-0)

- [x] Owner (Vitor): A1–A11 + mapping C — **"autorizado"** (05/10). Papéis de security e Hermes Gateway owner acumulados no owner neste contexto solo (registrado).
- [x] Security (papéis da tabela): A1, A4, A5, A7, A8, A11 — cobertos pela autorização do owner (acumulado).
- [x] Hermes Gateway owner: A1–A3, A8–A10 + **seleção formal do vocabulário autoritativo** (C — incl. authentication context/version behavior) — cobertos pela autorização do owner (acumulado).
- [x] Review independente sem BLOCKER/HIGH — ✅ re-review `PASS` (H1/M1/M2/L1–L3 resolvidos; N1–N3 aplicados).
- [x] Feeding `pd`: gate G-0 approved + wave-1 done + checkpoint (05/10).

**Autorizações de fase registradas:** G-1 (edição do checkout Hermes — série replayable, sem instalação): **"autorizado" (05/10)**; a execução da wave 2 inicia somente após o fechamento do G-0.
