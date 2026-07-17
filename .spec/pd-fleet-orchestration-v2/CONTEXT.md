# PD Fleet Orchestration V2 — Context

## Propósito

Fechar os gaps da review com uma camada local, segura, recuperável e determinística de execução de fleet. Este documento orienta implementação posterior; **não autoriza execução nesta branch**.

## Invariantes

- O plano normalizado é imutável durante um run; cada task tem ID único e contrato completo.
- Um `run_id` identifica uma tentativa lógica; `attempt` é monotônico por task. `completed` é terminal e nunca é reexecutado no resume.
- Toda mutação passa pelo `FleetRunStore`, com optimistic generation/ownership check, escrita atômica no mesmo filesystem, fsync quando aplicável e recuperação do último snapshot válido.
- Só o owner do run pode fazer transition/commit; lease expirado vira `orphaned`/`failed`, nunca sucesso implícito.
- Eventos e reports são append-only, redigidos e JSON-safe. `sequence` é a ordem de persistência/auditoria append-only; `query("events")` expõe a ordem canônica `(ordering_key, sequence)`. A ordem de conclusão do scheduler não é declarada determinística.
- Nenhuma task paralela sobrepõe `allowed_paths`, nem viola `forbidden_paths`; paths são relativos ao root declarado e traversal/links perigosos são recusados.
- Readiness depende de DAG, wave barrier, gates, inputs, capabilities e leases reconciliados.
- Report `completed` exige campos semânticos: status coerente, outputs requeridos, testes/evidência, decisão e timestamps de execução; `failed/blocked` exige motivo e blocker/error estruturado.
- Nenhum comando é executado por default. Shell, rede, subprocesso e provider são capacidades explícitas e negadas por padrão.
- Humanos aprovam o gate final; ferramenta não converte ausência de decisão em aprovação.

## Limites de segurança

**Permitido agora:** normalização, validação pura, store local, checkpoint, replay, simulação determinística e adapter local in-process.  
**Somente opt-in futuro:** `ValidationExecutor` com allowlist exata (argv sem shell), root/sandbox explícito, timeout, ambiente mínimo e captura redigida.  
**Não habilitado:** `ProviderAdapter` externo, rede, credenciais, shell genérico, comandos derivados de texto, dispatch automático.

## Ownership

- `scripts/pd_fleet/models.py`, `contracts.py`: contratos e normalização (owner: domain/contracts).
- `validation.py`, `lifecycle.py`: regras puras (owner: safety/state).
- `state.py`, `checkpoint.py`, novo `run_store.py`: persistência (owner: persistence).
- `orchestrator.py`, `dispatch.py`, novos executors/adapters: coordenação (owner: orchestration), sem persistência própria.
- `scripts/pd.py`: somente CLI adapter/compatibilidade (owner: CLI).
- `tests/fleet/`: cada tarefa possui arquivos de teste exclusivos; integrações em `tests/fleet/integration/` (Create).
- `.spec/pd-fleet-orchestration-v2/`: documentação V2; V1 intocável.

## Decisões arquiteturais

1. **Store antes de paralelismo:** scheduler só obtém lease e commita resultado pelo store; workers não mutam plano/CLI.
2. **Canonical model:** normalização transforma aliases e tipos aceitos num único JSON canônico, sem timestamp/path absoluto volátil.
3. **Reconciliation:** ao abrir run, comparar hash do plano, generation, tasks terminais, leases, checkpoints e eventos; divergência perigosa bloqueia.
4. **Validation boundary:** comando é dado não confiável. `DeclarativeValidation` apenas registra; executor separado exige policy `allowlist + sandbox + timeout`.
5. **Provider boundary:** protocolo capability-based e default-deny; factory retorna “disabled” salvo configuração explícita futura, sem fallback remoto.
6. **Deterministic concurrency:** selecionar IDs ordenados; executar bounded concurrent; bufferizar resultados; persistir/emitir em ordem canônica.
7. **Human gate:** gate `human_verification` requer `owner`, `identity` como string literal auditável, `decision`, `evidence_digest` e `freshness_window` (com timestamps); alterações reabrem gate. Autenticação criptográfica/identity provider são futuros e out-of-scope.
8. **Compatibilidade:** V1 load/read/CLI continuam; migração é opt-in e reversível.

## Identidade canônica e protocolo de reconciliation

O plano é canonicalizado removendo, antes da serialização, timestamps de runtime, paths absolutos (inclusive `/mnt/*`, home e variantes Windows) e secrets já redigidos. A serialização normativa é UTF-8 com `json.dumps(sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)`; NaN/Infinity são inválidos. `plan_hash` é SHA-256 em lowercase hex dos bytes `b"pd-fleet-plan:v2\\0" + canonical_json_utf8`, com prefixo/domínio e versão fixos. Assim, aliases/permutação de campos não alteram o digest, enquanto qualquer mudança semântica altera-o.

O protocolo de abertura/retomada é formalmente: `load -> parse -> canonicalize -> hash -> compare plan_hash -> compare generation/run/checkpoint/lease/event sequence -> block on mismatch -> claim -> use -> commit`. O bloqueio acontece antes de readiness/dispatch e antes de qualquer mutação; generation, run, checkpoint, lease e sequência de eventos stale ou divergentes são fail-closed. `claim` congela tokens de generation/lease para `use` e `commit`, e `commit` faz CAS. A matriz de testes exige fixtures/golden determinísticos, relógio e ambiente controlados, e cenários de drift/stale após load/hash que provem state/snapshot/events/evidence inalterados.

## Contrato do checker de paths/links (implementado)

O contrato possui `scripts/pd_fleet/v2_doc_paths.py` e `tests/fleet/test_v2_doc_paths.py`. O checker recebe `repo_root` explícito, é somente Python stdlib, offline e read-only. Ele analisa os documentos V2, extrai referências `Create`, `Exact files` e `Allowed paths` por item individual, exige existência ou `Create` na task que possui o path, rejeita ownership cruzado/ambíguo e todo path V1 (`.spec/pd-fleet-orchestration/`). Links internos relativos e âncoras devem resolver dentro do root; traversal, escape, destino ausente e symlink de root/documento são violações.

A saída deve ser JSON UTF-8 estável (ordenação de chaves/listas, `repo_root` relativo, sem timestamps/absolutos/segredos), com `schema_version`, `violations[{code,path,task,detail}]` e `summary`. Exit `0` = válido, `1` = violações, `2` = argumento/root inválido ou configuração inválida. O estado permanece **PARTIAL/OPEN** até review e gate humano.

## Contrato mínimo de estado V2

`schema_version`, `run_id`, `plan_hash`, `generation`, `owner`, `status`, `waves`, `tasks`, `leases`, `attempts`, `checkpoints`, `reports`, `events`, `gates`, `metrics`, `audit`, `updated_at`. O bloco legado continua preservado sem reinterpretar sua lista `tasks`.

## Baseline T2-01 (evidência executada)

O fixture `tests/fleet/test_v2_baseline.py` congela o handoff em `schema_version=pd-fleet-baseline:v2`, comando `pytest -q`, branch `feat/pd-fleet-orchestration-plan`, commit curto `2b4f219` e contagem histórica explícita `278`. A contagem não é uma asserção contra a suíte corrente: após adicionar os quatro testes do baseline, `pytest -q` retorna **282 passed**; esse drift é documentado, não mascarado.

O teste também captura branch/commit de forma sanitizada e impede claim global `PASS` sem gate aprovado e digest de evidência. A matriz V1→V2 permanece deliberadamente em `verified`, `partial`, `open` e `superseded`, sem converter planejamento ou suíte verde em aprovação V2. Evidência desta execução: targeted **4 passed** e suíte completa **282 passed**; compileall e diff-check são verificações de fechamento, não aprovação humana.
