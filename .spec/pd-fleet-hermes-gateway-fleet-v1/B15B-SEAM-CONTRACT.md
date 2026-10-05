# B15B — Seam Contract (B15b.1) — event publisher + principal resolution

**Status:** `draft_v0_1_for_review` — **nenhum patch aplicado**; a série replayable é o T-202 (G-1 aprovado). Canário TUI B15a.2 segue live; readiness live do Fleet segue `NOT_READY_HERMES_SEAM`.
**Data:** 2026-10-05 · **Autoria:** ISIS (orchestrator) · **Fonte:** `B15B-DECISION-MATRIX.md` (A1–A11/B/C) · `G1-CONTRACT.md` (§3–§9) · `G4-SECURITY` · `G4-CLOSURE` · `B15A-TUI-WIRE-CONTRACT.md` · `B15A-DELIVERY-RECOVERY-CONTRACT.md` · precedente `patches/0010-hermes-lazy-namespaced-tui-rpc-seam.patch`.
**Review independente:** a dispatchar (critério: sem BLOCKER/HIGH → T-202 desbloqueado).

## 1. Escopo e fronteira

O seam B15b.1 = **duas capacidades host-side no processo gateway**, lazy/namespaced/default-off (modelo: patch `0010` do B15a — staged registration):

1. **Event publisher** — publicação dos eventos de lifecycle metadata-only (allowlist v1) para um observer Fleet registrado.
2. **Principal resolution** — resolução server-side da cadeia de identidade (caller → profile/workspace → sessão → observer).

**Read-only:** sem dispatch, sem mutação de sessão, sem rota HTTP, sem enable em produção. **0 call sites** até ativação autorizada (pós-B15b.4).

## 2. Registration/dispatch contract (lazy, namespaced)

- **Modelo:** `register_fleet_bridge_observer(relative_name, callback)` — staged no manager (análogo a `register_tui_rpc` do 0010), namespaced sob o plugin (`pd-fleet-hermes.<relative_name>`).
- **Nome (proposta):** segmentos ASCII `[a-z0-9_-]`; sem `.` nas bordas, `..`, `/`; não pode iniciar com o nome do plugin; **colisão no registro ⇒ erro** (nunca overwrite silencioso); staging idempotente por nome; clear em reload (`force`).
- **Assinatura do handler (proposta):** `handler(event: FleetBridgeEvent, *, principal: ResolvedPrincipal) -> None` — o handler **nunca** recebe dados não-redigidos; é chamado fora do loop crítico do gateway.
- **Isolamento de exceção:** exceção do handler é **contida** no caller (erro bounded `handler_error`, log redigido); jamais derruba o loop do gateway, o canal ou outros handlers.
- **Versão:** wire `pd-fleet-gateway-bridge:v1`; handlers declaram suporte; versão não suportada ⇒ `unsupported_schema` (deny), **sem fallback**.
- **Disabled:** flag ausente/inválida ⇒ seam inerte (registro vazio, publisher no-op); config malformada/hot-reload **não amplia** acesso (re-validação a cada uso).

## 3. Principal resolution (server-side, deny-by-default)

- **Cadeia:** caller do canal (Discord/Telegram = identidade do adapter; API = boundary de token de sessão) → binding **owner/profile/workspace (Hermes-owned)** → sessão autoritativa (server-resolved) → observer principal Fleet.
- **Nenhum claim do caller** cria ou sobrescreve identidade (A1); ausência/ambiguidade ⇒ deny (`unauthenticated` / `foreign_owner`).
- **Auth context por camada — sem herança** (dashboard ≠ Fleet; TUI ≠ bridge); a matriz composite-deny (`B15B-DECISION-MATRIX` §B) é avaliada **por inteiro** (8 gates) a cada uso.
- `TokenPrincipal` / API key global **não** são identidade humana (A1).

## 4. Event publisher (envelope, allowlist, bounds, redaction)

- **Envelope:** `pd-fleet-gateway-bridge:v1` (G1 §4) — campos required; IDs/refs opacos e limitados; `event_origin` = `gateway_native` (nunca republicar derivado como nativo).
- **Allowlist v1 (G1 §5):** `session.registered` · `session.status_changed` · `session.heartbeat` · `session.metadata_changed` · `session.detached` · `session.ended` — payloads **fechados** (tabela G1 §5); unknown keys/values fail-closed.
- **Redaction ANTES de** buffer/persistência/outbox/replay/log/métrica/entrega (G4-SECURITY §5; allowlist por campo = A11). Deny-list: prompts, histórico, tool args/results, provider material, credenciais, tokens, terminal, paths, URLs, valores de identidade.
- **Bounds (blocker #4 — candidatos propostos a congelar na revisão):** payload ≤4KiB · envelope ≤8KiB · replay ≤100 eventos (G4-CLOSURE §2); **candidatos novos:** depth ≤8 · cardinalidade de listas ≤32 · strings ≤512 · opaque refs ≤128 · sem mapas arbitrários · control/bidi Unicode, binário, NaN/∞ rejeitados.
- **Ordering/epoch/sequence:** conforme `B15A-DELIVERY-RECOVERY-CONTRACT` (associação/epoch/sequence contíguo; snapshot-before-stream; gap explícito `replay_gap`/`cursor_stale`; `resync_required` só quando boundary não comprovável).

## 5. Error taxonomy (referência normativa)

`G1-CONTRACT.md` §7 é **normativo** (códigos canônicos). O seam usa **apenas** esses códigos; diagnósticos contêm somente código estável + refs opacos; **nunca** revelam existência de sessão não-scoped.

## 6. Fixtures e testes de compatibilidade (nomeados — critério de saída do B15b.1)

| Fixture | Verifica |
|---|---|
| `default_off_no_handlers` | sem flag ⇒ 0 handlers registrados, publisher no-op, 0 call sites |
| `config_absent_disabled_invalid` | deny sem widening (composite-deny §B) |
| `golden_non_fleet` | plugins/handlers não-Fleet inalterados (sem regressão) |
| `handler_exception_isolated` | handler que levanta ⇒ gateway continua; erro bounded; log redigido |
| `namespace_rejections` | nomes inválidos/colisão rejeitados no staging |
| `version_unsupported` | envelope v1 aceito; não suportada ⇒ `unsupported_schema` |
| `redaction_by_field` | fixtures por campo da allowlist (A11) — executadas no B15b.2 |
| `replay_epoch_crash_matrix` | matriz da delivery-recovery contract — executada no B15b.4 |

## 7. O que este contrato NÃO autoriza

- **Nenhum patch é aplicado por este documento.** T-202 prepara a série replayable (git am limpo **em cópia**, sem instalação) sob G-1.
- Instalação/ativação no checkout vivo = pedido separado (pós-B15b.4). Live validation = B15b.5 (G-3). `local_verified` nunca substitui `NOT_READY_HERMES_SEAM`.
