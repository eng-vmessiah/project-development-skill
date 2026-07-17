# PD Fleet Orchestration V2 — Context

## Propósito

Fechar os gaps da review com uma camada local, segura, recuperável e determinística de execução de fleet. Este documento orienta implementação posterior; **não autoriza execução nesta branch**.

## Invariantes

- O plano normalizado é imutável durante um run; cada task tem ID único e contrato completo.
- Um `run_id` identifica uma tentativa lógica; `attempt` é monotônico por task. `completed` é terminal e nunca é reexecutado no resume.
- Toda mutação passa pelo `FleetRunStore`, com optimistic generation/ownership check, escrita atômica no mesmo filesystem, fsync quando aplicável e recuperação do último snapshot válido.
- Só o owner do run pode fazer transition/commit; lease expirado vira `orphaned`/`failed`, nunca sucesso implícito.
- Eventos e reports são append-only, redigidos, JSON-safe e ordenados por `(sequence, task_id)`; concorrência não define ordem observável.
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

## Contrato mínimo de estado V2

`schema_version`, `run_id`, `plan_hash`, `generation`, `owner`, `status`, `waves`, `tasks`, `leases`, `attempts`, `checkpoints`, `reports`, `events`, `gates`, `metrics`, `audit`, `updated_at`. O bloco legado continua preservado sem reinterpretar sua lista `tasks`.
