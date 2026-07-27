# Multi-Plan Decomposition

Estratégia para decompor uma **visão de produto** em múltiplos planos de execução interdependentes, com ordenação clara.

## Quando usar

- A visão é grande demais para um plano único (> 1 sprint, > 10 tarefas)
- Existem dependências claras: A precisa existir antes de B
- Diferentes aspectos exigem skills/abordagens diferentes

## O Padrão: Foundation → Tooling → Product

### 1. Foundation (Motor / Engine)
O que tudo depende — a camada mais funda. Sem ela, nada mais funciona.

**Características:**
- Libs, engines, primitivas reutilizáveis
- Refatoração de código existente em padrões genéricos
- Geralmente não entrega valor visível ao usuário final

**Exemplo:** `wizard-engine` — motor de wizard conversacional extraído do profile wizard existente.

### 2. Tooling (CLI / DevX)
Ferramentas de qualidade que garantem que o produto não alucina/quebra.

**Características:**
- CLIs determinísticas, testes, validadores
- Modo sem-LLM para testar fluxos
- CI/CD, smoke tests

**Exemplo:** `wizard-cli` — CLI determinística que testa wizards sem LLM, evitando alucinações em produção.

### 3. Product (Feature)
O que o usuário final vê e usa. Consome Foundation e usa Tooling para garantir qualidade.

**Características:**
- Interfaces de usuário (WhatsApp, web)
- Autenticação, segurança, UX
- Valor direto pro negócio

**Exemplo:** `customer-portal` — usuários administram seus recursos por uma interface dedicada.

## Estrutura de Cada Plano

Cada plano deve incluir:

```markdown
# [Nome] — Plano de Implementação

> **Depende de:** [planos que precisam existir primeiro]
> **Dependido por:** [planos que dependem deste]

**Goal:** [Uma frase]

**Architecture:** [2-3 frases]

**Skills utilizadas:**
- writing-plans — plano bomb-proof
- codebase-design — módulos profundos
- tdd — RED-GREEN-REFACTOR
- (etc.)

---

## Tasks (com checkboxes)
- [ ] Task 1
- [ ] Task 2
```

## Fluxo de trabalho

1. **Decompor** a visão nos 3 layers (foundation, tooling, product)
2. **Criar planos** na ordem inversa de dependência (foundation primeiro)
3. **Revisar** cada plano com o stakeholder
4. **Commitar** todos os planos na main
5. **Criar worktrees/branches** por plano
6. **Executar** na ordem de dependência

## Exemplo real

Visão: "Usuários administrarem recursos por um portal dedicado"

```
Decomposição:
├── wizard-engine (foundation) — motor de wizard genérico
├── wizard-cli (tooling) — CLI determinística anti-alucinação
└── customer-portal (product) — interface de administração para usuários

Execução: wizard-engine → wizard-cli → customer-portal
```

## Erros comuns

- **Pular o foundation** — começar pelo produto e depois tentar extrair a base (refatoração dolorosa)
- **Pular o tooling** — features sem CLI/teste determinístico = alucinação não detectada
- **Planos muito grandes** — se um plano tem > 15 tasks, talvez precise decompor mais
- **Dependências implícitas** — sempre declarar `Depende de:` e `Dependido por:`
