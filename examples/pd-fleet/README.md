# Fleet local end-to-end

`run_local.py` executa o manifest de exemplo sem providers: lê apenas um arquivo
YAML/JSON local, valida `FleetPlan`, cria `AgentContract`s e usa o adapter
`simulated` determinístico do `Dispatcher`. Não há shell, `subprocess`, rede,
credenciais ou leitura/escrita implícita fora do diretório indicado.

## Executar

A partir da raiz do repositório:

```bash
python examples/pd-fleet/run_local.py \
  --plan examples/pd-fleet/plan.yaml \
  --output /tmp/pd-fleet-output
```

`--output` é obrigatório para tornar o escopo de escrita explícito. O processo
retorna `0` somente quando todas as tasks e os gates locais passam; manifest
inválido, task incompleta ou gate reprovado retorna `1`. JSON também é aceito:

```bash
python examples/pd-fleet/run_local.py --plan ./plan.json --output ./tmp-output
```

YAML requer PyYAML instalado; JSON não tem essa dependência.

## Outputs

Todos os arquivos abaixo são determinísticos (inclusive timestamps de exemplo) e
ficam sob `--output`:

- `contracts.json`: contratos normalizados por task;
- `results/<task-id>.json`: resultado do dispatch simulado;
- `reports.json`: `AgentReport`s por agente/task;
- `evidence.json`: evidências declarativas produzidas pelos resultados locais;
- `gates.json`: `GateResult`s para `review`, `grill`, `smoke_test` e `evidence`;
- `summary.json`: estados da orquestração e status avaliado de cada gate.

O exemplo não executa os `validation_commands` do manifest: eles são apenas dados
validados pelo contrato. Assim, mesmo ao apontar para um diretório temporário,
nenhum arquivo do repositório é alterado.

## Limites, ameaça e rollback

Este exemplo é **local/simulado**, não um provider ou executor externo. Nunca
inclua tokens, URLs privadas ou credenciais no manifest. O plano é entrada não
confiável: IDs e outputs ficam contidos no output explícito; traversal, symlink,
shell, rede e comandos derivados de texto são proibidos. O modo V2 geral continua
**PARTIAL/OPEN**, sem alegação de G6 PASS.

Para migração, mantenha o estado V1 e execute em um output/namespace V2 separado.
Para rollback, interrompa o processo e invalide leases antes de remover apenas o
output V2. Preserve `evidence.json`/reports (e seus digests) em armazenamento de
auditoria antes da limpeza; não altere o plano ou estado legado. Um
executor futuro só pode ser habilitado por policy explícita, allowlist, sandbox,
timeout, limites e redaction.
