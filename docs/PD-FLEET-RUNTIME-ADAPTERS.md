# PD Fleet Runtime Adapters

**Status:** local contract verified — default-deny; Hermes integration pending
**Decision:** `fleet_core_standalone_hermes_thin_plugin`

> O Fleet Core permanece independente de Hermes. `pd-fleet-hermes` será um plugin/adapter fino e opt-in; não conterá scheduler, persistência, DAG, checkpoints, gates ou reports genéricos.

## Princípio

> Hermes adiciona capacidades ao Fleet; Hermes não define o que o Fleet é.

O `pd` Core e o Fleet local não podem depender de Hermes. O núcleo deve funcionar para usuários que:

- usam somente planejamento/spec/gates;
- executam um Fleet local/simulado;
- usam Hermes;
- usam OpenCode, Claude Code ou outro runtime no futuro.

## Camadas

```text
PD Core
  spec · plan · DAG · contratos · gates · decisões humanas
        ↓ opcional
PD Fleet
  scheduler · lifecycle · state · leases · reports · checkpoints · reconciliation
        ↓ adapter selecionado
Runtime Adapter
  none · local · hermes · opencode · claude · outro
```

O Core não importa Hermes. O Fleet não assume que existe Gateway, provider, credencial, sessão remota ou rede.

## Hermes plugin boundary

A integração Hermes será empacotada como um adapter/plugin opcional, conceitualmente
chamado `pd-fleet-hermes`. Ele não é o Fleet Core e não é necessário para `pd-only`
ou `fleet-local`.

```text
~/.hermes/plugins/pd-fleet-hermes/
  plugin.yaml
  __init__.py
```

Na primeira versão B15a, o plugin pode registrar somente hooks de lifecycle Hermes
aprovados pelo seam público; não registra tools invocáveis pelo modelo, comandos
slash/CLI ou RPC fora desse seam. Ele deve ser fino: scheduler, persistência Fleet,
checkpoints, DAG, gates e reports genéricos continuam no pacote do Fleet e devem
funcionar fora do Hermes.

A descoberta/instalação do plugin é separada e sua ativação exige `plugins.enabled`.
Isso não autoriza efeitos live por si só; as flags e gates do Fleet continuam obrigatórios.

O contrato inicial do plugin segue o formato público `plugin.yaml` + `register(ctx)`
e começa com hooks de lifecycle. O plugin não deve auto-instalar dependências, gravar
estado no próprio diretório, criar shims globais, registrar tools invocáveis pelo modelo
ou acessar rede/credenciais/provider/subprocessos por padrão. RPC namespaced do TUI
depende de um seam explícito do Hermes, pois não é oferecido pelo `PluginContext` atual.

## Modos operacionais

### `pd-only`

Somente planejamento e validação:

```yaml
pd:
  enabled: true
fleet:
  enabled: false
```

Permite spec, plano, DAG, validação, gates e estado de planejamento. Não despacha tasks.

### `fleet-local`

Coordenação local/simulada:

```yaml
pd:
  enabled: true
fleet:
  enabled: true
  runtime: local
  dispatch: simulated
  external_effects: deny
```

É o modo de referência para exemplos e testes. Deve provar lifecycle, retry, reports, checkpoints, resume e paralelismo sem credenciais, rede ou provider externo.

### `fleet-hermes`

Integração Hermes opcional:

```yaml
fleet:
  enabled: true
  runtime: hermes
  dispatch: injected
  external_effects: deny
hermes:
  integration: tui
  observer_enabled: false
```

A integração live continua exigindo seus próprios gates. `tui`, `api` e `gateway` são superfícies diferentes e não devem ser confundidas.

### Futuras integrações

```yaml
fleet:
  enabled: true
  runtime: opencode  # ou claude/outro adapter
```

A ausência de um adapter deve produzir `UNSUPPORTED_RUNTIME_CAPABILITY` ou `BLOCKED_RUNTIME_NOT_CONFIGURED`, não falha de instalação do PD.

## Contrato mínimo de adapter

O contrato deve ser pequeno e capability-based. Um adapter pode implementar somente observação, somente execução local ou ambos:

```python
class RuntimeAdapter(Protocol):
    def capabilities(self) -> Capabilities: ...
    def start_task(self, request: TaskRequest) -> TaskHandle: ...
    def get_status(self, handle: TaskHandle) -> TaskStatus: ...
    def collect_report(self, handle: TaskHandle) -> AgentReport: ...
    def stop(self, handle: TaskHandle) -> None: ...
```

Capacidades Hermes específicas não podem ser presumidas pelo Fleet:

```text
session_observe
session_attach
session_replay
session_lifecycle
provider_dispatch
```

O scheduler deve verificar a capability antes de usá-la e bloquear de forma explícita quando ela não existir.

## Regras de compatibilidade

- `pd` CLI deve iniciar e validar sem Hermes instalado.
- `fleet-local` não deve importar ou iniciar Hermes.
- Hermes não deve ser necessário para `run_local.py`, testes ou documentação do Fleet V2.
- O adapter Hermes deve ficar isolado em módulo/pacote próprio.
- Tickets, principals, sessões e eventos Hermes não entram no modelo genérico do Fleet.
- O runtime adapter não pode substituir gates, aprovação humana ou decisão do PD Core.
- `fleet.enabled` não deve, sozinho, permitir efeitos externos.
- Toda transição para `dispatch: live` exige gate e autorização separados.

## Roadmap de implementação

1. Manter `pd-only` e `fleet-local` como caminhos suportados e verificáveis.
2. Extrair/confirmar uma interface capability-based de adapter no Fleet.
3. Criar um adapter local explícito para o exemplo e testes de contrato.
4. Testar ausência de Hermes como cenário de primeira classe.
5. Tratar B15a/B15b como trilha `fleet-hermes` opcional e empacotada como plugin Hermes:
   - B15a: plugin `pd-fleet-hermes` + `tui_gateway`, sessão única, stdio/JSON-RPC;
   - B15b: o mesmo plugin + Gateway/API de mensagens, multi-sessão/global.
6. Só depois planejar adapters OpenCode/Claude/outros conforme necessidade real.

## Estado atual

O contrato de Runtime Adapter e o caminho fake/local independente de Hermes estão implementados e verificados localmente. O Fleet V2 como produto continua experimental e default-deny. O bridge Hermes permanece em `NOT_READY_HERMES_SEAM`; essa limitação não deve degradar o funcionamento do PD Core ou do Fleet local.

Evidência local atual: suíte `tests/fleet` verde; a contagem exata deve ser atualizada junto com cada nova regressão. Essa evidência não implica provider/runtime Hermes, dispatch live, produção ou aprovação de promoção.
