# Cockpit BTG — benchmark of a mission control plane

**Status:** benchmark (observation of a third-party product, not its specification)
**Purpose:** extract portable contracts for PD Fleet / ISIS core. This is **not** a clone target.
**Source:** screen recording, 143.19 s, 864x496 @30fps (WhatsApp compression), photographed off a
monitor — not a screen capture. Frames preserved outside this repo.
**Analysis of record:** `/home/vitor/isis-obsidian/Projects/cockpit-btg/ANALISE-VIDEO-2026-10-25.md`
(two independent passes; second pass: 286 frames at 2 fps + RapidOCR upscale).

## Evidence rules used here

| tag | meaning |
|---|---|
| `confirmed` | legible on a frame **and** read twice (visual + OCR) |
| `inferred` | one source only (one frame, or OCR alone) |
| `assumed` | reported by the owner; no frame shows it |

Text on a photographed monitor is unreliable at character level. Two claims in the source analysis
were re-read and contradicted each other (`71%` vs `77%`; `Renegociação` vs `Recuperação` on the
conclusion screen) — **that screen is low confidence and no number from it should be quoted as fact**.
For a demo with fixture data the stakes are low; for a spec they are not.

## What the product is

A **mission control plane** for engineering/data work executed by agents, installed into a local
workspace repository. A mission produces artifacts in the workspace; SQLite holds the event store;
every entity carries an ID. Sequence: grill (adversarial interview) -> discovery -> plan ->
orchestration plan -> projection plan -> execution -> conclusion with a verdict.

The demo observed is a **single-file HTML** app with a hash router
(`file:///.../cockpit-demo-completo (1).html#/m/MIS-.../<tab>`), `confirmed` by OCR of the URL bar in
three frames. Production stack is `inferred` at best; the demo runs with `Fake Execution`,
`Ambiente Local (Mock)` and sessions literally named `fake future`.

## Portable contracts

### 1. Route — work type decided before the plan `confirmed`

Three routes with different pipelines, and the route is recorded on the mission
(`Rota registrada: Investigação · Ledger v15 · nenhum runtime iniciado`):

| route | pipeline |
|---|---|
| Investigation | investigation plan -> spike -> review -> analytical conclusion -> archive. **Can conclude without ever dispatching a worker.** |
| Implementation | DDD -> SDD -> implementation plan -> plan cockpit -> approval -> dispatch |
| Hybrid | investigation plan -> spike -> review -> implementation only if needed |

The portable idea is not the naming, it is the **negative rule**: an investigation mission is a
legitimate mission that spends no dispatch budget.

### 2. Three plans `assumed` (owner statement; only the projection is visible)

mission plan (goal, waves, tasks, acceptance, expected evidence) -> orchestration plan (wave ->
task -> owner -> attempt -> session -> worker, dependencies and gates) -> projection plan (what the
cockpit displays). The projection being derived from the plan — not hand-authored — is the part that
matters: the UI cannot show a metric the plan did not declare.

### 3. Execution tree `confirmed`

`Task -> Attempt (generation) -> Session -> Worker -> Tool call`, one row per node with
`Agente/LLM/acao`, `Status`, `Linha do tempo` (bars, striped = long running) and a score.
Observed shape:

```
MIS-...  Plano ...
|- Cockpit Orchestrator (sem Sessao)
|- Observer (read-only)
TASK-BASELINE                 Concluido
|- Attempt #1 geracao 1
   |- SES-01  Sucesso
      |- W-01 ISIS - Claude sonnet - OpenCode   Concluido
         |- athena.query                       Concluido
TASK-RECONCILE-RESIDUAL       Em andamento
   |- SES-02 fake future - fake-llm            On hold/Modificado
      |- W-02                                  Em andamento
         |- athena.query  Concluido
         |- athena.ctas   em execucao
```

The orchestrator row explicitly says **sem Sessao**, and the tree says `Sessao sem worker` where it
applies: the absence is a node, not a blank.

### 4. Effect reconciliation — the strongest idea in the product `confirmed`

Header of the screen: `Efeito desconhecido em W-02 - athena.ctas`. Node panel:

- `Efeito pode ou nao ter ocorrido. nao reporta.`
- `Operacao: athena.ctas`, `payload-hash: e9f2c77a6...`, `Receipt: assinado`
- Lineage: `Avo: SES-02`, `Pai: W-02`, `Filhos (0): nenhum`
- Two buttons: **`Nao foi executado`** / **`Foi executado`**

A tool call that cannot prove its own effect becomes an explicit *unknown* state that requires a
human verdict, recorded with the payload hash. The system never guesses "probably worked".

### 5. Event taxonomy `<entity>.<verb>`, past tense, with a source `confirmed`

Seven of 85 events visible in the frame: `mission.created`, `plan.versioned`,
`spike.completed`, `review.completed`, `gate.requested`, `checkpoint.created`, `text.integrity`
(`U+FFFD detectado em mission.json`). Columns: `Hora - Tipo - Resumo - Fonte`.
The log is the backbone: attention panel, operations panel, checkpoint and conclusion all derive
from it.

### 6. Context ledger — versioned, counted `confirmed`

Chips: `Fatos 3 - Decisoes 6 - Premissas 2 - Restricoes 2 - Perguntas abertas 1` (total 14,
`Ledger v15`). Entries carry provenance (`origem: discovery - C1`). Open questions are first-class
entities, not footnotes.

### 7. Artifacts — md+json pair, hash, age, sensitivity, version `confirmed`

Columns `Artefato - Kind - conteudo - Gerado - Sensibilidade`. Rows: `context`, `grill`,
`domain-model` (ddd), `system-design` (sdd), `plan` (**v2**, supersedes v1), `spike-report`,
`review`, `checkpoint` — each as `.md` + `.json`, with a truncated `sha256:...`, age (`ha 3 d`) and
`sensibilidade: internal`.

### 8. Provider capability matrix, selection per session `confirmed` (labels partly `inferred`)

Columns: `Provider - Transporte - Estado - startSession - sendPrompt - subscribe - Receipt`.
Rows: `FakeProvider` (future), `vscode-copilot` (Debug Log/ACP), `opencode` (ACP/HTTP/CLI),
`claude-code` (future). States are `observe`/`future`; capabilities are `supported` /
`unsupported` / `nao validado`, and the footnote states that a missing capability is reported as
missing — **never as implicit success** — and that provider selection is per session, not global.

## Explicitly not portable

Login/SSO, Jira-style tracker, n8n, the BTG domain (athena/CROS), the fixture scaffolding
(`fake future`, `fake-llm`), and any visual identity. The demo file itself is not on this machine;
there is no source to copy and none is needed.

## Material handling

The frames contain a corporate e-mail, intranet URL and internal workspace names. They stay in the
Obsidian vault: **not** in this repo, not published, and the browser chrome is cropped before any
external use.
