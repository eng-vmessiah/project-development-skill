# Phase Closeout — Checklist para Encerrar uma Fase PD

Depois que o código está implementado e testado, closeout é o processo de:
1. Verificar que tudo está íntegro
2. Separar o que pertence à feature do que são mudanças não relacionadas
3. Atualizar a documentação de estado
4. Commitar e push
5. Registrar no diário e memória

Use este checklist quando: testes passam, review foi feito, e você está pronto para "fechar o ciclo".

---

## Step 1 — Verificar estado do repositório

```bash
# Estado geral
git status

# Mudanças não stageadas
git diff --stat HEAD

# Arquivos novos não rastreados
git ls-files --others --exclude-standard
```

## Step 2 — Separar arquivos da feature de mudanças não relacionadas

Quando você tem múltiplas modificações no working tree, algumas da feature atual e outras de esforços paralelos:

```bash
# Listar arquivos modificados
git diff --name-only HEAD
git ls-files --others --exclude-standard

# Decidir quais pertencem à feature com base em:
# 1. O PLAN.md lista este arquivo?
# 2. O SPEC.md menciona esta área?
# 3. O commit message precisa incluir esta mudança?
```

Stagear **apenas** os arquivos da feature:

```bash
git add \
  .spec/minha-feature/ \
  path/to/new/file1.py \
  path/to/new/file2.py \
  path/to/modified/file.py \
  ...
```

Deixe os arquivos não relacionados (outra feature, outro esforço) como modified/untracked — eles serão commitados separadamente.

## Step 3 — Atualizar STATE.md

STATE.md deve refletir o estado exato do projeto ANTES do commit:

```markdown
## Phase
7 (Merge — Complete)   # ou a fase atual

## Status
complete

## Completed Deliverables

| Sub-wave | What | Status |
|----------|------|--------|
| 1 | Feature X | ✅ testes |
| 2 | Feature Y | ✅ testes |

## Quality Gates
- Security scan: ✅ Clean
- Test suite: N/N passed
- Fresh-eyes review: ✅

## Checkpoints
- YYYY-MM-DD HH:MM: Último checkpoint

## Timestamps
- Created: YYYY-MM-DDTHH:MM:SS
- Updated: YYYY-MM-DDTHH:MM:SS   # AGORA
```

### Regras de versionamento de STATE.md

| Situação | Phase | Status |
|----------|-------|--------|
| Especificação aprovada | 2 (Planning) | approved |
| Codificando | 4 (Coding) | coding |
| Código pronto, revisando | 6 (Review) | review |
| Commit feito, entregue | 7 (Merge) | complete |

## Step 4 — Static Security Scan

```bash
# Hardcoded secrets
git diff --cached | grep "^+" | grep -iE "(api_key|secret|password|token|passwd)\s*=\s*['\"][^'\"]{6,}['\"]" || echo "✅ Clean"

# Shell injection
git diff --cached | grep "^+" | grep -E "os\.system\(|subprocess.*shell=True" || echo "✅ Clean"

# SQL injection
git diff --cached | grep "^+" | grep -E "execute\(f\"|\.format\(.*SELECT" || echo "✅ Clean"

# eval/exec
git diff --cached | grep "^+" | grep -E "\beval\(|\bexec\(" || echo "✅ Clean"
```

**Se qualquer scan falhar:** pare, corrija, re-stage. Não commite com secrets.

## Step 5 — Verificar testes

```bash
python -m pytest -v --tb=short 2>&1 | tail -5
```

- Confira que são N passed, 0 failed
- Se houver falhas: pare, corrija, não commite

## Step 6 — Commitar

### Estrutura do commit message

```
[verified] <prefixo>: <descrição curta>

<parágrafo opcional com detalhes>

<bullet points do que foi feito>

Quality: N/N testes, security scan limpo, fresh-eyes review
Files: N arquivos, +/-N linhas
```

### Prefixos comuns

| Prefixo | Quando usar |
|---------|-------------|
| `feat:` | Nova funcionalidade |
| `fix:` | Correção de bug |
| `refactor:` | Refatoração sem mudança de comportamento |
| `docs:` | Documentação |
| `chore:` | Manutenção, build, tooling |
| `test:` | Testes novos ou corrigidos |
| `[verified]` | Prefixo **obrigatório** quando passou por fresh-eyes review |

### Exemplo real

```
[verified] isis-omni-extraction: Phase 1 + Phase 2 completos

Phase 1 — Router Evolution:
- Circuit Breaker (2 falhas → cooldown exponencial) + LKGP
- GET /api/arena/capabilities (8 testes)
- MCP Server stdio com 5 tools

Phase 2 — Security + Evaluation + A2A:
- Guardrails/PII Masker (22 testes)
- Eval Framework (17 testes)
- A2A Metadata (trace + policy na resposta)

Quality: 77/77 testes, security scan limpo, fresh-eyes review
Files: 24 arquivos, +2210 linhas novas
```

## Step 7 — Push

```bash
git push
git status  # MUST show "up to date with origin"
```

**Regra:** Se o push falhar, resolva e retry. Não deixar trabalho no disco sem push.

## Step 8 — Registrar no diário do projeto

Escrever uma entrada no diário ou registro de projeto adotado pelo repositório, com:

```
## HH:MM — <Título>

### O que foi feito
- Feature 1: descrição
- Feature 2: descrição

### Arquivos principais criados
- path/to/file1.py — descrição
- path/to/file2.py — descrição

### Qualidade
- Testes: N/N passando
- Security scan: ✅
- Commit: <hash>

### Pendências
- Coisas que ficaram pra depois
```

## Step 9 — Registrar na memória

Use `memory action=add target=memory` para registrar o fato durável sobre o que foi concluído.

---

## Anti-patterns

| Anti-pattern | Problema |
|---|---|
| Commitar arquivos não relacionados na mesma feature | Histórico poluído, difícil reverter |
| Pular security scan | Risco de vazar secrets |
| Pular STATE.md | Sessão seguinte não sabe onde está |
| Não fazer push | Trabalho perdido se WSL reiniciar |
| Commit message genérico ("fixes", "updates") | Impossível entender o que foi feito depois |
| Pular nota diária | Perde contexto para sessões futuras |

## Referências

- `requesting-code-review` — processo detalhado de fresh-eyes review (security scan, two-axis review, auto-fix loop)
- `pd` — o pipeline completo (este arquivo é uma referência do skill pd)
