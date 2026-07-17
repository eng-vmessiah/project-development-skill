# Agent Report: `<task-id>`

Use este relatório ao concluir (ou bloquear) uma task. O conteúdo deve ser
reproduzível por outro subagent e auditável por uma pessoa.

## Contract

- **Task ID:** `<id>`
- **Wave:** `<wave>`
- **Role:** `<role>`
- **Owner:** `<agent-id>`
- **Status:** `pending` | `ready` | `running` | `blocked` | `failed` | `completed` | `skipped`
- **Capabilities:** `<capabilities exigidas>`
- **Objective:** `<resultado observável>`
- **Depends on:** `<task-ids ou —>`
- **Parallel group:** `<grupo ou —>`
- **Allowed paths:** `<paths autorizados>`
- **Forbidden paths:** `<paths proibidos>`
- **Inputs:** `<artefatos/paths de entrada>`
- **Retry policy:** `<max_attempts, backoff_seconds, retryable_errors>`

## Result

- **Summary:** `<o que foi feito ou por que foi bloqueado>`
- **Acceptance criteria:**
  - [ ] `<critério 1>` — `<evidência>`
  - [ ] `<critério 2>` — `<evidência>`
- **Outputs:**
  - `<artefato/path>` — `<descrição e evidência>`

## Scope and changes

- **Allowed paths:** `<paths autorizados>`
- **Forbidden paths respected:** `yes` | `no` — `<detalhes se no>`
- **Files changed:**
  - `<path>` — `<mudança>`

## Validation evidence

```text
Command: <comando exato>
Result: PASS | FAIL
Output: <saída relevante, resumida ou completa>
```

Repeat the block for every validation command executed.

## Risks and blockers

- **Risks:** `<risco residual ou none>`
- **Blockers:** `<blocker, decisão pendente ou none>`
- **Retry recommendation:** `<retry_policy aplicada/recomendação>`

## Handoff

- **Next task(s):** `<task-ids ou —>`
- **Evidence location:** `<path/link ou —>`
- **Reported at:** `<YYYY-MM-DDThh:mm:ssZ>`
