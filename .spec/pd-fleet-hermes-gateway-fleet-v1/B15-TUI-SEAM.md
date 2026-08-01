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

## Padrão de plugin adotado

O audit de `agentiker-scout` confirmou o formato operacional esperado para plugins
Hermes: `plugin.yaml` + `__init__.py` com `register(ctx)`, usando as APIs públicas do
`PluginContext`. Adotamos somente o formato e os testes de carregamento, não a
superfície ampla do plugin externo.

Regras adicionais para `pd-fleet-hermes`:

- a primeira versão registra somente hooks de lifecycle; não registra tools invocáveis pelo modelo;
- não instala dependências automaticamente durante o carregamento;
- não escreve estado persistente no diretório do plugin;
- não cria shims globais em `sys.modules`;
- não acessa rede, credenciais, provider ou subprocesso por padrão;
- usa contrato de carregamento versionado e testes para plugin ausente, desabilitado e habilitado;
- qualquer estado Fleet permanece no Fleet Core e em sua persistência própria.

Essas regras reduzem a superfície de efeitos colaterais observada no plugin de
referência e preservam a separação entre adapter e Fleet Core.

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

The first B15a version may register only the approved lifecycle hooks through the public plugin API. It must not register model-invocable tools, slash/CLI commands, or runtime RPC handlers outside the separately approved Hermes RPC seam. It must call the generic Fleet API and keep Fleet state, scheduler, checkpoints, DAG, gates, and reports outside the plugin. If the plugin is absent or disabled, Hermes and the standalone Fleet paths must continue to work normally.

## B15a — TUI local por sessão

Implementar atrás de flag default-off e sem alterar o comportamento normal:

1. Implementar primeiro o seam B15a.0 de registro RPC namespaced, com teste de plugin ausente/desabilitado.
2. Resolver a sessão authoritative dentro de `tui_gateway.server`.
3. Adicionar operações locais explícitas `activate/status/deactivate`, com owner derivado server-side. Esses nomes pertencem ao control plane TUI; não são os nomes do bridge G1.
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

### Contract blockers before implementation

The following are required design gates, not assumptions to be filled in by the implementer:

| Boundary | Required decision/evidence |
|---|---|
| RPC seam | public registration signature, namespace collision, exception isolation, versioning, disabled/absent behavior, and non-Fleet golden tests |
| identity | trusted binding for stdio connection, TUI process, profile, workspace, active session, and observer; ambiguity/absence must deny |
| effective enablement | plugin allow-list + integration flag + supported seam + authenticated caller + explicit association + capability + lifecycle state; all are mandatory |
| payload | closed allow-list, byte/depth/cardinality bounds, control/Unicode policy, bounded diagnostics, and redaction before buffer/persistence/log/replay |
| delivery | snapshot boundary, opaque server-issued cursor, epoch, retention/tombstone, replay gap, outbox/ack, heartbeat/TTL/grace, and restart behavior |
| lifecycle | state machine and authority for attach, reconnect, deactivate, session end, TUI exit, crash, and in-flight RPCs |

Candidate values from G4 remain candidates only: 5-minute activation TTL, 90-second association idle TTL, 30-second heartbeat, 15-minute cursor TTL, 60-second reconnect grace, 4 KiB payload, 8 KiB envelope, and 100-event replay batch. They require owner/security approval before becoming normative.

## Local/injected B15a.2 first RPC contract

A contract-only slice now exists in `scripts/pd_fleet/tui_readonly_contract.py`. It
is intentionally not a live Hermes RPC and does not change the plugin package.
The local method candidate is:

```text
pd-fleet.session.snapshot
```

The request is closed and contains only:

```json
{
  "session_id": "server-compatible-opaque-ref",
  "schema_version": "pd-fleet-tui-session:v1"
}
```

The host resolves authentication, ownership, capability, profile/workspace,
association, and authoritative session binding. None of those fields may be
provided by the TUI client. The injected binding must be authenticated,
`user_owned_session`, and carry `observe_session_metadata`; otherwise the
contract fails closed.

The bounded response is limited to `method`, `schema_version`, `redacted`,
`capability`, and a session object containing only `session_ref`,
`association_ref`, `ownership_mode`, `status`, `stream_epoch`, `sequence`, and
`metadata_version`. Prompts, history, tools, providers, credentials, paths,
owner/profile/workspace identity, and arbitrary metadata are excluded.

Focused local evidence: `tests/fleet/test_tui_readonly_contract.py` — `9
passed`, including bounded capability collection checks. This proves only pure
request/binding/response validation. It does not
prove Hermes host authentication, session resolution, transport registration,
TUI compatibility, replay, restart, or live readiness.

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
