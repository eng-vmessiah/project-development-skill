---
name: create-implementation-plan
description: >-
  Create structured implementation plans for new features, refactoring,
  or upgrades. Produces machine-readable, step-by-step plans optimized
  for autonomous AI execution. Use before multi-file changes to scope
  work, sequence tasks, and define verification criteria.
  Complements the GSD `plan-phase` command.
---

# Create Implementation Plan — Standard Edition

Cria planos de implementação multi-arquivo no formato que o Hermes
Agent (e outros AIs) podem executar autonomamente.

---

## Formatos Suportados

| Formato | Quando usar | Exemplo |
|---|---|---|
| **PD** (`PLAN.md` + checkpoints) | Features using the standard PD format | `plans/<feature>/PLAN.md` |
| **Repository-native** (`plan.md` + project checkpoints) | Projects with an established planning format | `plans/active/<feature>/plan.md` |

Ambos os formatos compartilham a mesma estrutura de tasks, verificação
e pós-implantação. A diferença é o diretório e o layout do checkpoint.

---

## Formato PD

```
plans/
└── <feature-name>/
    ├── PLAN.md              — Plano principal
    └── checkpoints.md       — Status tracking (✅/🔄/⏳)
```

### Template PLAN.md

```md
---
title: "Implementação: [feature]"
status: "draft"
created: "YYYY-MM-DD"
estimated_effort: "[small|medium|large]"
---

# Plano: [feature]

## Escopo

### Inclui
- [item 1]

### Não inclui
- [item 1]

## Dependências
- [pré-requisito 1]

## Tasks

### Task 1: [Nome]
**Arquivos:** `path/to/file1.ts`

**O que fazer:**
- [passo detalhado 1]

**Verificação:**
```bash
comando
```

## Ordem de Execução
1. Task 1

## Pós-implantação
- [ ] Testes passando
- [ ] Build limpo
```

---

## Formato nexus-vellum

```
plans/active/<feature-slug>/
├── plan.md              — Plano com Goal + Architecture + File Structure + Tasks
└── checkpoints.md       — Tabelas de verificação por task
```

### Template plan.md

```md
# [Feature] — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development ...

**Goal:** [uma frase]

**Architecture:** [breve descrição da abordagem técnica]

**Tech Stack:** [tecnologias relevantes]

---

## File Structure

| Path | Action | Responsibility |
|---|---|---|
| `path/to/file.ts` | Create/Modify | O que faz |

---

## Pre-flight (one-time)

- [ ] **Step P1:** [verificação prévia]
- [ ] **Step P2:** [snapshot/se salva]

---

## Task 1: [Nome]

**Files:**
- Create/Modify: `path/to/file.ts`

**What to do:**
1. [passo]
2. [passo]

**Verification:**
```bash
comando
```
```

### Template checkpoints.md

```md
# [Feature] — Checkpoints

> Legenda: ✅ done · 🔄 in progress · ❌ blocked · ⏸️ skipped · ⏳ pending

**Branch:** `feat/<feature>`

---

## Task 1 — [Nome]

- Status: ⏳
- Data: —
- Commit: —

| # | Verificação | Como Testar | Critério |
|---|------------|-------------|----------|
| 1.1 | [o quê] | [comando] | [critério] |
```

---

## Análise de Codebase (gap analysis)

Antes de criar um plano de melhoria, é recomendado fazer uma análise
de gaps do projeto atual. O workflow:

1. **Explorar estrutura** — `find` dos arquivos, ler `AGENTS.md`, `ARCHITECTURE.md`
2. **Identificar gaps ativos** — comparar `plans/active/` com anti-patterns conhecidos (AGENTS.md, `docs/ARCHITECTURE.md` riscos)
3. **Verificar cobertura** — testes existentes, CI blocking, observabilidade, segurança
4. **Priorizar** — P1 (cego em produção) > P2 (qualidade) > P3 (performance)
5. **Criar planos** — um diretório `plans/active/<gap>/` por gap, com `plan.md` + `checkpoints.md`

Faça uma análise do codebase antes de definir os caminhos e contratos do plano.

---

## Níveis de Detalhe

| Esforço | Tasks | Detalhe por Task |
|---|---|---|
| **Small** (1-2 arquivos) | 1-3 tasks | 2-3 passos cada |
| **Medium** (3-6 arquivos) | 3-6 tasks | 3-5 passos cada |
| **Large** (7+ arquivos, refactor) | 5-10 tasks | 5-8 passos cada, com rollback |

---

## Boas Práticas

- **Tasks atômicas** — cada task produz um commit
- **Ordem explícita** — dependências claras entre tasks
- **Verificação automatizada** — comandos bash para validar cada task
- **Escopo negativo** — dizer explicitamente o que NÃO está incluso
- **Rollback** — tasks destrutivas devem ter plano de reversão
- **Contexto mínimo** — o plano deve ser executável sem consultar o criador
- **Pre-flight sempre** — verificar estado atual antes de começar (snapshot, baseline)

---

## Integração com GSD

Este skill complementa o comando `/gsd-plan-phase`:

```
GSD plan-phase → gera PLAN.md em .planning/phases/<N>/
  ├── pode ser refinado com este skill para tasks mais detalhadas
  └── verificação via /gsd-verify-work depois da execução
```

---

## Quick Reference

```bash
# PD format
mkdir -p plans/<feature-name>
cat > plans/<feature-name>/PLAN.md << 'EOF'
# Plano: ...
EOF

# nexus-vellum format
mkdir -p plans/active/<feature-slug>
cat > plans/active/<feature-slug>/plan.md << 'EOF'
# Feature — Plan
EOF
```

---

# Specification Files

Create structured spec files in `/spec/` with format optimized for AI consumption. Specs define requirements, constraints, and interfaces in unambiguous Markdown.

## Spec Directory Structure

```
spec/
├── spec-schema-<name>.md        — Data schema / models
├── spec-tool-<name>.md          — Hermes tool definition
├── spec-data-<name>.md          — Data pipeline / storage
├── spec-infra-<name>.md         — Infrastructure / deployment
├── spec-architecture-<name>.md  — System architecture
├── spec-design-<name>.md        — UI / UX design
└── spec-process-<name>.md       — Processes and workflows
```

## Spec Template

```md
---
title: "[Concise Title]"
type: "[schema|tool|data|infra|architecture|design|process]"
status: "[draft|review|approved]"
created: "[YYYY-MM-DD]"
---

# Spec: [Title]

## Objective
[What this spec defines, in 2-3 sentences]

## Requirements

### Functional
- [RF1]: [description]

### Non-functional
- [RNF1]: [performance, security, etc.]

### Constraints
- [C1]: [technical or business limitation]

## Interface

### Inputs
| Field | Type | Required | Description |
|---|---|---|---|
| `field` | `string` | yes | ... |

### Outputs
| Field | Type | Description |
|---|---|---|
| `result` | `object` | ... |

## Expected Behavior

### Happy path
1. [step 1]

### Edge cases
- [case 1]

## Dependencies
- [dep 1]
```

## When to Use Which

| Situation | Document Type |
|-----------|--------------|
| New Hermes tool | `spec-tool-<name>.md` |
| New PostgreSQL table | `spec-schema-<name>.md` |
| New React component | `spec-design-<name>.md` |
| New agent workflow | `spec-process-<name>.md` |
| Data pipeline | `spec-data-<name>.md` |
| Infra change | `spec-infra-<name>.md` |
| Overall architecture | `spec-architecture-<name>.md` |

**Spec best practices:** Precise language, examples and edge cases, self-contained, clear separation of requirements vs constraints, structured format for parsing.
