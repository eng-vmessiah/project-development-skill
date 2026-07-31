# B15 — TUI Gateway como primeiro Hermes live seam

**Status:** `decision_approved_plan_only`
**Readiness:** `NOT_READY_HERMES_SEAM`
**Authorization:** planejamento e implementação local/injetada somente; sem conexão ao runtime ativo, sem credenciais e sem rollout

## Decisão de arquitetura

O primeiro caller Hermes real a ser investigado para Fleet será o backend local da TUI:

```text
React/Ink TUI
  ↕ newline-delimited JSON-RPC / stdio
`tui_gateway.entry` → `tui_gateway.server`
  ↕ sessão Hermes authoritative
Fleet observer
```

O `tui_gateway` não é um segundo `isis-gateway.service`. Ele é um backend local, normalmente filho da TUI, que já possui um transporte JSON-RPC por stdio, lifecycle de sessão e publicação de eventos para o cliente TUI.

O Gateway de mensagens/API permanece uma segunda etapa (`B15b`) e não deve ser inferido como resolvido por esta integração.

## Descoberta de implementação — pré-requisito B15a.0

A inspeção do Hermes confirmou que `tui_gateway.server` registra RPCs por decorators
internos (`@method(...)`) e que o `PluginContext` atual oferece hooks, commands e
tools, mas não oferece um registro público de RPC. Portanto, `pd-fleet-hermes` não
pode adicionar `fleet.*` somente pela API atual de plugins.

Antes de B15a, será necessário um seam mínimo no Hermes/TUI para registro explícito
de RPCs namespaced e default-off. Esse seam deve:

- aceitar somente handlers registrados pelo plugin habilitado;
- manter o namespace `fleet.*` separado dos RPCs existentes;
- não expor ticket bruto, principal ou credencial ao TypeScript;
- manter o comportamento byte-for-byte quando o plugin estiver ausente/desabilitado;
- rejeitar métodos Fleet quando a flag de integração estiver desligada;
- não mover scheduler, persistência, DAG, checkpoints, gates ou reports para o Hermes.

Esse item é uma extensão de infraestrutura do Hermes para suportar o plugin; não é
implementação do Fleet Core nem autorização de live dispatch.

## Por que o TUI vem primeiro

- caller local e acionado explicitamente pelo usuário;
- escopo inicial pode ser limitado à sessão ativa;
- identidade e lifecycle são resolvidos no backend Python, sem confiar no TypeScript;
- não exige começar por uma nova superfície HTTP pública;
- facilita canary, replay, detach e rollback por processo/sessão.

## Plugin boundary

B15 should be implemented as the Hermes integration plugin/adapter `pd-fleet-hermes`,
not by moving the Fleet orchestrator into Hermes core or into `tui_gateway.server`.
The plugin is installed/discovered separately and explicitly enabled with Hermes'
`plugins.enabled` allow-list. Plugin enablement is necessary for the integration to
load, but is not sufficient authorization for live effects; Fleet flags and gates
remain authoritative.

The plugin may register tools, slash/CLI commands, and Hermes lifecycle hooks. It
must call the generic Fleet API and keep Fleet state, scheduler, checkpoints, DAG,
gates, and reports outside the plugin. If the plugin is absent or disabled, Hermes
and the standalone Fleet paths must continue to work normally.

## B15a — TUI local por sessão

Implementar atrás de flag default-off e sem alterar o comportamento normal:

1. Implementar primeiro o seam B15a.0 de registro RPC namespaced, com teste de plugin ausente/desabilitado.
2. Resolver a sessão authoritative dentro de `tui_gateway.server`.
3. Adicionar uma operação RPC explícita de ativação/status/desativação, com owner derivado server-side.
4. Emitir/consumir a capacidade de ativação somente no backend Hermes; o ticket bruto não atravessa para a TUI TypeScript.
5. Associar o observer a uma única `session_ref` ativa.
6. Entregar à TUI somente eventos Fleet redigidos e bounded.
7. Implementar reconnect, cursor/replay, gap, TTL, detach e session-end.
8. Revogar e limpar a associação quando a sessão ou o processo terminarem.
9. Manter `NOT_READY_HERMES_SEAM` até haver teste contra o caminho real do `tui_gateway` e revisão de segurança.

### Critérios de B15a

- ativação só pode ser iniciada pelo caller autorizado do backend;
- owner/principal não pode ser fornecido pelo cliente TUI;
- escopo não pode escapar da sessão ativa;
- eventos não podem conter prompt, histórico, tool output, credencial ou token;
- reconnect não cria associação duplicada;
- replay com cursor inválido/gap falha fechado e produz diagnóstico bounded;
- session end, TUI exit e Gateway crash revogam ou invalidam a associação;
- flag off mantém o comportamento atual byte-for-byte no caminho não Fleet;
- testes Python do `tui_gateway` e testes do cliente TUI cobrem o protocolo RPC;
- canary local reproduzível prova attach → evento → replay → detach → cleanup.

## B15b — Gateway de mensagens/API

Somente depois de B15a aprovado localmente, avaliar o caminho do `api_server`/Gateway principal:

- caller autenticado de Discord/Telegram/API;
- registration/activation por usuário e sessão;
- subscription global ou escopo multi-sessão;
- transporte autenticado e associação durable;
- replay/rollback operacional no processo `isis-gateway.service`.

B15b exige decisão separada do owner Hermes, revisão de segurança e autorização explícita de live validation.

## Não objetivos

- não transformar o TUI em Fleet global;
- não reutilizar o canal de dashboard como descoberta global;
- não habilitar `pd_fleet_gateway_enabled` em produção;
- não expor o ticket ao TypeScript ou a um endpoint público;
- não conectar automaticamente a TUI ao `isis-gateway.service`;
- não tratar o TUI como solução para o caminho Discord/Telegram.

## Risco operacional

A TUI usa Node/Ink e o backend pode criar subprocessos auxiliares. O incidente de OOM do WSL não prova causalidade da TUI, mas B15a deve incluir observação de memória de Node, `tui_gateway`, slash workers e subprocessos MCP antes de qualquer canary prolongado.
