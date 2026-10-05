# B15B — Seam Contract (B15b.1) — event publisher + principal resolution

**Status:** `v0_3_installed` — patch B15b.1 **INSTALADO** no checkout vivo (`966a079d9c`, 05/10; **inert** — 0 call sites; default-off provado live). Rollback: `dc50153faf`. Canário TUI B15a.2 segue live; readiness live do Fleet segue `NOT_READY_HERMES_SEAM`.
**Data:** 2026-10-05 · **Autoria:** ISIS (orchestrator) · **Fonte:** `B15B-DECISION-MATRIX.md` (A1–A11/B/C) · `G1-CONTRACT.md` (§3–§9) · `G4-SECURITY` · `G4-CLOSURE` · `B15A-TUI-WIRE-CONTRACT.md` · `B15A-DELIVERY-RECOVERY-CONTRACT.md` · **mecanismo vivo:** `tui_gateway/plugin_rpc.py` + `tui_gateway/fleet_tui_registration.py` (checkout `dc50153faf`).
**Review independente:** v0.1 → `PASS_WITH_BLOCKERS`; v0.2 → **`PASS`**; v0.3 = congelamento dos bounds. **T-202 review: `PASS`** (zero BLOCKER/HIGH/MEDIUM; replay reproduzido independentemente; LOW-1/LOW-3 adjudicados nesta revisão; LOW-2/LOW-4 aceitos p/ B15b.1).

## 1. Escopo e fronteira

O seam B15b.1 = **duas capacidades host-side no processo gateway**, **default-off e boot-gated** (NÃO lazy — ver §2):

1. **Event publisher** — publicação **outbound** dos eventos de lifecycle metadata-only (allowlist v1) para um observer Fleet registrado.
2. **Principal resolution** — resolução server-side da cadeia de identidade (conexão → processo → profile/workspace → sessão → observer).

**Mecanismo a estender (ancorado no VIVO):** o registry real do checkout — `tui_gateway/plugin_rpc.py` (`PluginRpcRegistry`: namespace **exato** `fleet`; identificadores `^[a-z][a-z0-9_]*$`; `enabled=True` obrigatório; batch atômico) — e o padrão de composição do canário (`fleet_tui_registration.py`: `register_plugin_rpc_batch("fleet", …, enabled=…)` no boot). O patch `0010` (staging lazy `pd-fleet.*`) é **histórico de worktree — NÃO é a base**.

**Base pinada:** live tip **`dc50153faf`** (`~/.hermes/hermes-agent`). T-202 desenvolve em **worktree**, gera a série replayable e prova `git am` limpo **em cópia** — sem instalação.

**Read-only:** sem dispatch, sem mutação de sessão, sem rota HTTP, sem enable em produção. **0 call sites** até ativação autorizada (pós-B15b.4).

## 2. Registration/dispatch contract (namespaced, boot-gated)

- **Superfície (proposta):** registro de observers **irmão** do `PluginRpcRegistry` (mesmo módulo/padrão — ex.: `register_fleet_bridge_observers`, batch), com a **mesma disciplina do registry vivo**: namespace **exato** `fleet`; identificadores `^[a-z][a-z0-9_]*$` (sem `-`, sem maiúsculas); `enabled=True` obrigatório (senão `PluginRpcRegistrationError`); **batch atômico** (tudo validado antes de publicar; swap único de referência); `callable` obrigatório.
- **Colisão/duplicata (semântica do registry vivo):** nome em `reserved` ⇒ `namespace collision`; duplicata no registry ⇒ `duplicate`; duplicata no batch ⇒ erro — **nunca overwrite silencioso**; batch vazio ainda valida o namespace.
- **Assinatura do handler (proposta):** `handler(event: FleetBridgeEvent, *, principal: ResolvedPrincipal) -> None` — nunca recebe dados não-redigidos; chamado fora do loop crítico do gateway.
- **Isolamento de exceção (padrão vivo):** exceção do handler é **contida** no caller (o dispatch de plugin vivo usa `-32000 "plugin RPC handler error"` — **diagnóstico interno, NÃO código da taxonomia §5**); log redigido; jamais derruba o loop do gateway, o canal ou outros handlers.
- **Trigger (boot-gated, não lazy):** o publisher é **outbound** — não há request para "descobrir" registro; a registration ocorre **uma vez no boot**, sob o flag **`pd_fleet_gateway_enabled`** (padrão do canário: composition root avalia o flag no boot). Sem flag ⇒ registry vazio, publisher no-op, 0 call sites.
- **Versão:** wire `pd-fleet-gateway-bridge:v1`; handlers declaram suporte; versão não suportada ⇒ `unsupported_schema` (deny), **sem fallback**.
- **Disabled:** flag ausente/inválida ⇒ seam inerte; config malformada/hot-reload **não amplia** acesso (re-validação a cada uso).

## 3. Principal resolution (server-side, deny-by-default)

- **Cadeia:** conexão → **processo** → binding **owner/profile/workspace (Hermes-owned)** → sessão autoritativa (server-resolved) → observer principal Fleet (fonte do caller: Discord/Telegram = identidade do adapter; API = boundary de token de sessão).
- **Nenhum claim do caller** cria ou sobrescreve identidade (A1); ausência/ambiguidade ⇒ deny (`unauthenticated` / `foreign_owner` / `association_required` — gates B4–B8 da matriz §B).
- **Auth context por camada — sem herança** (dashboard ≠ Fleet; TUI ≠ bridge); a matriz composite-deny (`B15B-DECISION-MATRIX` §B) é avaliada **por inteiro** (8 gates) a cada uso.
- `TokenPrincipal` / API key global **não** são identidade humana (A1).

## 4. Event publisher (envelope, allowlist, bounds, redaction)

- **Envelope:** `pd-fleet-gateway-bridge:v1` (G1 §4) — campos required; IDs/refs opacos e limitados; `event_origin` = `gateway_native` (nunca republicar derivado como nativo).
- **Allowlist v1 (G1 §5):** `session.registered` · `session.status_changed` · `session.heartbeat` · `session.metadata_changed` · `session.detached` · `session.ended` — payloads **fechados** (tabela G1 §5); unknown keys/values fail-closed.
- **Redaction ANTES de** buffer/persistência/outbox/replay/log/métrica/entrega (G4-SECURITY §5; allowlist por campo = A11). Deny-list: prompts, histórico, tool args/results, provider material, credenciais, tokens, terminal, paths, URLs, valores de identidade, **approval payloads, env vars**.
- **Bounds (blocker #4 — CONGELADOS pelo review `PASS` da v0.2, 05/10; base 4KiB/8KiB/100 = candidatos G4-CLOSURE §2, propostos como normativos — não embutir em runtime antes da ativação autorizada):** payload ≤4KiB · envelope ≤8KiB · replay ≤100 eventos · depth ≤8 · cardinalidade ≤32 · strings ≤512 · opaque refs ≤128 · diagnóstico ≤512 · sem retry automático no seam (política do caller via taxonomia §5) · normalização: Unicode NFC; rejeitar control/bidi, binário, NaN/∞; sem mapas arbitrários.
- **Ordering/epoch/sequence:** conforme `B15A-DELIVERY-RECOVERY-CONTRACT` (associação/epoch/sequence contíguo; snapshot-before-stream; gap explícito `replay_gap`/`cursor_stale`; `resync_required` só quando boundary não comprovável). **Partição explícita:** cursor/retention/tombstones/outbox/ack/heartbeat/restart → B15b.3/.4.

## 5. Error taxonomy (referência normativa)

`G1-CONTRACT.md` §7 é **normativo** (códigos canônicos) para toda superfície wire. O seam usa **apenas** esses códigos em respostas; diagnósticos internos (ex.: `-32000` de handler) **não são taxonomia** e nunca cruzam a fronteira wire. Diagnósticos wire contêm somente código estável + refs opacos; **nunca** revelam existência de sessão não-scoped.

## 6. Fixtures e testes de compatibilidade (nomeados — critério de saída do B15b.1)

| Fixture | Verifica |
|---|---|
| `default_off_no_handlers` | sem flag ⇒ 0 registros, publisher no-op, 0 call sites |
| `config_absent_disabled_invalid` | deny sem widening (composite-deny §B) |
| `golden_non_fleet` | plugins/handlers não-Fleet inalterados (sem regressão) |
| `handler_exception_isolated` | handler que levanta ⇒ gateway continua; diagnóstico interno contido; log redigido |
| `namespace_rejections` | §2: namespace exato, charset, `reserved`/duplicata — rejeitados no registro |
| `version_unsupported` | envelope v1 aceito; não suportada ⇒ deny silencioso no seam (0 entregas); **código canônico `unsupported_schema` no publisher real (B15b.3/.4)** |
| `bounds_frozen` | cada bound do §4 tem fixture nomeada (incl. diagnóstico/normalização) — **executada quando os bounds forem embutidos (B15b.3/.4); §4 proíbe pré-ativação** |
| `redaction_by_field` | fixtures por campo da allowlist (A11) — executadas no B15b.2 |
| `replay_epoch_crash_matrix` | matriz da delivery-recovery contract — executada no B15b.4 |

## 7. O que este contrato NÃO autoriza

- **Nenhum patch é aplicado por este documento.** T-202 prepara a série replayable contra a **base `dc50153faf`** (git am limpo **em cópia**, sem instalação) sob G-1.
- Instalação/ativação no checkout vivo = pedido separado (pós-B15b.4). Live validation = B15b.5 (G-3). `local_verified` nunca substitui `NOT_READY_HERMES_SEAM`.
