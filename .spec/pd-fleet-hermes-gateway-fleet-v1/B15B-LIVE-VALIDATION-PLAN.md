# B15B — Plano de Validação Live (pacote G-3)

**Status:** `draft_v0_1_for_authorization` — gate **G-3** (owner: Vitor). **NADA será executado antes da aprovação.**
**Data:** 2026-10-05 · **Autoria:** ISIS · **Fonte:** `B15B-PLAN.md` §4 (B15b.5) · T-501 (`B15B-REPLAY-ROLLBACK.md`) · `G4-AUTH-LIFECYCLE.md` §10.

## 1. Escopo proposto (slice mínimo)

Instalação do **seam B15b.1** (`patches/b15b-seam/0001-…patch`) no checkout vivo `~/.hermes/hermes-agent` + validação de invariantes **default-off** + estabilidade do gateway. **Sem ativação de publisher** (não existe — fases futuras): o seam é **inerte por construção** (0 call sites, registry vazio sem wiring).

## 2. Passos propostos

1. **Preflight (read-only):** checkout limpo na ref `dc50153faf`; health do gateway; snapshot do canário B15a.2.
2. **Instalar a série:** `git am patches/b15b-seam/0001-…patch` no checkout vivo (revertível: ref pré-instalação registrada).
3. **Sanidade:** import do módulo no venv do runtime + `tests/tui_gateway/test_plugin_observer.py` (**7/7**) no checkout vivo.
4. **Restart do `isis-gateway.service`** — procedimento **ensaiado no T-501** (stop → verify → start → verify). **Downtime declarado: janela 10–20 min** (efetivo esperado ~1–3 min; margem p/ rollback).
5. **Fixtures negativas live:**
   - gateway saudável pós-restart (Discord/Telegram reconectados — log);
   - **default-off vivo:** registry de observers vazio no processo (probe read-only); `publish` ⇒ no-op (0 entregas);
   - registro sem flag ⇒ **erro** (fail-closed);
   - **canário B15a.2 intacto:** fleet TUI resolve exatamente 1 sessão (preservado);
   - `hermes-serve` **intocado** (não reiniciar — canário).
6. **Evidence packet** com buckets separados (`contract`/`fake`/`TUI`/`seam`/`live`) → `B15B-LIVE-EVIDENCE.md`.
7. **Rollback pronto:** `git reset` do checkout à ref pré-instalação + restart do gateway se necessário (procedimento T-501).

## 3. Não-objetivos (explícitos)

- Sem publisher/ativação de eventos (wiring live não existe — fases futuras).
- Sem tocar `hermes-serve` (canário ligado) nem config do gateway (tokens/canais).
- `local_verified` **não** substitui `NOT_READY_HERMES_SEAM` — o closeout (T-602) avalia o que **foi** validado, com buckets separados.

## 4. Riscos e mitigações

| Risco | Mitigação |
|---|---|
| Gateway não volta pós-restart | Procedimento ensaiado (T-501); rollback = restart manual; canais reconectam com token existente |
| Import falha no venv vivo | Passo 3 **antes** do restart; se falhar ⇒ rollback sem restart |
| Sessão do agente morre | `isis-gateway` ≠ `hermes-serve` (sessão vive no serve); restarts do gateway já ocorreram antes, independentes |
| Checkout vivo sujo | Preflight exige `git status` limpo; **aborta** se não |

## 5. Autorização (G-3) — checklist do owner

- [ ] Aprovar o escopo (§1/§2) e a instalação no checkout vivo (§2.2).
- [ ] Aprovar a janela de downtime (10–20 min) e **quem executa o restart** (proposta: **eu executo** com sua autorização; alternativa: **você executa** e eu conduzo o resto).
- [ ] Aprovar as fixtures negativas live (§2.5).

**Efeito:** G-3 aprovado ⇒ T-601/T-602 desbloqueados (execução do plano + closeout com G4 live closure).
