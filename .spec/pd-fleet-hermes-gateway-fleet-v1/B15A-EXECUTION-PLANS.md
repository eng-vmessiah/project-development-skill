# B15a — Execution Plans

**Status:** `planning_started`
**Readiness:** `NOT_READY_HERMES_SEAM`
**Mode:** local/injected planning first; no live Hermes activation, provider calls, credentials, subprocess control, push, merge, release or deploy.
**Depends on:** G8 local closeout already recorded in `VERIFICATION.md`.
**Blocks:** B15b messaging/API Gateway integration.

## Goal

Decompor B15a em ondas pequenas e verificáveis para conectar o Fleet ao backend TUI do Hermes por uma única sessão ativa, começando pelo seam de RPC namespaced que hoje não existe no `PluginContext` público.

## Current facts

- Fleet local/fake está verificado, mas não é evidência de readiness live.
- O adapter Hermes existente é read-only e retorna `NOT_READY_HERMES_SEAM` para operações sem seam suportado.
- `tui_gateway.server` usa RPCs internos por decorators; o `PluginContext` atual oferece hooks, commands e tools, não registro público de RPC.
- O plugin deverá seguir `plugin.yaml` + `register(ctx)` e lifecycle hooks only na primeira versão.
- A autorização atual proíbe modificar `/home/vitor/.hermes/hermes-agent`; B15a.0 fica como plano/bloqueio externo até autorização e owner Hermes.

## Dependency graph

```text
B15a.0 Hermes/TUI RPC seam
        │
        ▼
B15a.1 pd-fleet-hermes loading + lifecycle-only contract
        │
        ▼
B15a.2 session-scoped TUI Fleet protocol
        │
        ▼
B15a.3 security review + fake/local canary + B15a closeout
        │
        └──► B15b messaging/API Gateway (separate decision; not started)
```

---

## Plan B15a.0 — Hermes/TUI namespaced RPC seam

**Owner:** Hermes runtime/TUI owner
**Status:** `blocked_external_seam`
**Execution boundary:** design and contract review may happen here; implementation requires the Hermes checkout and explicit authorization.

### Objective

Adicionar um registro explícito, namespaced e default-off para handlers `fleet.*`, sem alterar o comportamento quando o plugin está ausente/desabilitado.

### Required contract

- aceitar somente handlers do plugin habilitado;
- manter `fleet.*` separado dos RPCs existentes;
- resolver principal/sessão no backend Python;
- não expor ticket bruto, principal ou credencial ao TypeScript;
- rejeitar métodos Fleet quando a flag estiver desligada;
- preservar comportamento non-Fleet byte-for-byte;
- não mover scheduler, DAG, persistência, checkpoints, gates ou reports para Hermes.

### Planned files (external; not to edit yet)

- `tui_gateway/server.py` — ponto de registro/dispatch, após discovery do código real.
- módulo público de plugin/RPC do Hermes — caminho exato a confirmar no checkout real.
- testes Python do `tui_gateway` — casos enabled/disabled/absent/unknown namespace.
- testes do cliente TUI — somente protocolo, sem identidade ou ticket bruto.

### Gate B15a.0

`BLOCKED` até haver: caminho real confirmado, contrato revisado pelo owner Hermes, testes default-off passando e autorização explícita para tocar o checkout Hermes.

---

## Plan B15a.1 — Plugin loading e lifecycle-only

**Owner:** PD/Fleet adapter
**Depends on:** B15a.0 contract accepted
**Status:** `pending`

### Objective

Criar o esqueleto opt-in `pd-fleet-hermes` com carregamento versionado e hooks de lifecycle somente, sem efeitos colaterais proibidos.

### Planned artifacts

- `pd-fleet-hermes/plugin.yaml` — metadata, versão de contrato e default-off.
- `pd-fleet-hermes/__init__.py` — `register(ctx)` mínimo usando API pública.
- `tests/.../test_plugin_loading.py` — plugin ausente, disabled, enabled, malformed e duplicate load.
- documentação B15 — contrato, limites e matriz de efeitos proibidos.

### Acceptance criteria

- absent/disabled não quebra `pd-only` nem `fleet-local`;
- enabled registra apenas lifecycle hooks;
- nenhum tool model-invocable é registrado;
- import/load não acessa rede, credenciais, provider, subprocesso ou estado persistente no diretório do plugin;
- contrato versionado rejeita versão incompatível de forma explícita e fail-closed.

### Verification

Executar testes focados de loading, teste de import side effects e suite local do adapter. Resultado esperado: pass; qualquer efeito proibido é blocker.

---

## Plan B15a.2 — Protocolo Fleet TUI por sessão

**Owner:** PD/Fleet adapter + Hermes/TUI owner
**Depends on:** B15a.0 e B15a.1
**Status:** `pending`

### Objective

Implementar observação Fleet read-only limitada à sessão authoritative ativa do TUI.

### Ordered tasks

1. Resolver sessão no backend; cliente não fornece `session_ref`, owner ou principal.
2. Implementar RPC explícito de activate/status/deactivate default-off.
3. Associar no máximo uma observação à sessão ativa e rejeitar escopo cruzado.
4. Emitir eventos Fleet versionados, bounded e redigidos.
5. Implementar cursor/replay/reconnect/gap/TTL/stale sem duplicar associação.
6. Executar detach em deactivate, session-end, TUI exit e crash/restart invalidation.

### Acceptance criteria

- attach → event → replay → detach → cleanup é determinístico;
- prompt, histórico, tool output, token, credencial e ticket bruto nunca aparecem na projeção TUI;
- cursor inválido/gap falha fechado com diagnóstico bounded;
- reconnect não cria associação duplicada;
- qualquer capacidade não suportada retorna `NOT_READY_HERMES_SEAM`.

### Verification

Testes Python do backend, testes de protocolo do cliente e canary fake/injetado; depois teste bounded contra o caminho real TUI somente quando B15a.0 estiver aprovado.

---

## Plan B15a.3 — Segurança, canary e closeout

**Owner:** PD/Fleet + security reviewer
**Depends on:** B15a.2
**Status:** `pending`

### Objective

Produzir evidência independente de que B15a é localmente seguro, reversível e não promove readiness live por engano.

### Required review

- default-deny e flag off;
- owner/principal server-side;
- redaction recursiva e payload bounds;
- replay/cursor/TTL/restart;
- ausência de rede, credenciais, provider, subprocesso e persistência indevida;
- rollback/desativação sem deixar associação órfã;
- observação de memória de Node, `tui_gateway`, workers e subprocessos MCP antes de canary prolongado.

### Gate B15a closeout

Somente `local_verified`/`local_canary_verified` se toda a evidência estiver anexada. Mesmo aprovado localmente, o resultado live continua `NOT_READY_HERMES_SEAM` até os owners Hermes/security fecharem a autorização correspondente.

---

## B15b — Explicitly not started

B15b cobre Gateway de mensagens/API, caller autenticado Discord/Telegram/API, escopo multi-sessão/global, transporte auth, associação durable, replay operacional e rollback do `isis-gateway.service`. É uma decisão separada e não é consequência automática de B15a.

## Planning gates

- [x] Reconciliar branch, commit e worktree.
- [x] Registrar handoff da sessão.
- [x] Decompor B15a com dependências explícitas.
- [ ] Revisão independente do plano sem BLOCKER/HIGH.
- [ ] Aprovação humana do plano.
- [ ] Autorização separada para editar checkout Hermes, se B15a.0 for executado.
- [ ] Iniciar implementação somente após os gates acima.
