---
name: spike
description: "Disposable experiments to validate an idea before committing to a build. Validate feasibility, compare approaches, surface unknowns. Also covers quick prototypes to answer a single design question (logic or UI)."
version: 1.2.0
author: Hermes Agent (adapted from gsd-build/get-shit-done, mattpocock/skills)
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [spike, prototype, disposable, feasibility, exploration, proof-of-concept, design, ui]
    related_skills: [sketch, subagent-driven-development, plan, prototype]
argument-hint: "What needs a spike or quick prototype?"
---

# Spike

**Leading word: disposable** — a spike exists to be thrown away. If you catch yourself cleaning it up for production, you've missed the point. The value is the verdict, not the code.

Use this when the user wants to **feel out an idea** before committing to a real build — validating feasibility, comparing approaches, or surfacing unknowns that no amount of research will answer.

**Completion criterion:** You have a verdict (VALIDATED / PARTIAL / INVALIDATED) per spike, captured in its README.md, with evidence and a recommendation.

Load this when the user says things like "let me try this", "I want to see if X works", "spike this out", "before I commit to Y", "quick prototype of Z", "is this even possible?", or "compare A vs B".

## When NOT to use this

- The answer is knowable from docs or reading code — just do research, don't build
- The work is production path — use the `plan` skill instead
- The idea is already validated — jump straight to implementation

## If the user has the full GSD system installed

If `gsd-spike` shows up as a sibling skill (installed via `npx get-shit-done-cc --hermes`), prefer **`gsd-spike`** when the user wants the full GSD workflow: persistent `.planning/spikes/` state, MANIFEST tracking across sessions, Given/When/Then verdict format, and commit patterns that integrate with the rest of GSD. This skill is the lightweight standalone version for users who don't have (or don't want) the full system.

## Core method

### 0. Quick prototype mode (pergunta única)

Se o usuário já sabe exatamente **uma** pergunta que quer responder — sem decomposição em múltiplos spikes — use a via rápida:

1. **Identifique a pergunta.** Qual decisão de design esse prototype vai responder?
2. **Pick a branch:**
   - **"Does this logic / state model feel right?"** → build um terminal app interativo que exercita a state machine
   - **"What should this look like?"** → gere várias variações radicais de UI (ver "Modo UI" no Build)
3. **Build rápido.** Um arquivo, um comando pra rodar. Sem persistência, sem polimento.
4. **Capture.** Veredito no README.md, commit num branch descartável. A resposta é o que importa, não o código.

Pule direto pro Build — não precisa de Research nem Decompose.

---

### 1. Decompose (modo completo, múltiplas perguntas)

Break the user's idea into **2-5 independent feasibility questions**. Each question is one spike. Present them as a table with Given/When/Then framing:

| # | Spike | Validates (Given/When/Then) | Risk |
|---|-------|----------------------------|------|
| 001 | websocket-streaming | Given a WS connection, when LLM streams tokens, then client receives chunks < 100ms | High |
| 002a | pdf-parse-pdfjs | Given a multi-page PDF, when parsed with pdfjs, then structured text is extractable | Medium |
| 002b | pdf-parse-camelot | Given a multi-page PDF, when parsed with camelot, then structured text is extractable | Medium |

**Spike types:**
- **standard** — one approach answering one question
- **comparison** — same question, different approaches (shared number, letter suffix `a`/`b`/`c`)

**Good spike questions:** specific feasibility with observable output.
**Bad spike questions:** too broad, no observable output, or just "read the docs about X".

**Order by risk.** The spike most likely to kill the idea runs first. No point prototyping the easy parts if the hard part doesn't work.

**Skip decomposition** only if the user already knows exactly what they want to spike and says so. Then take their idea as a single spike.

### 2. Align (for multi-spike ideas)

Present the spike table. Ask: "Build all in this order, or adjust?" Let the user drop, reorder, or re-frame before you write any code.

### 3. Research (per spike, before building)

Spikes are not research-free — you research enough to pick the right approach, then you build. Per spike:

1. **Brief it.** 2-3 sentences: what this spike is, why it matters, key risk.
2. **Surface competing approaches** if there's real choice:

   | Approach | Tool/Library | Pros | Cons | Status |
   |----------|-------------|------|------|--------|
   | ... | ... | ... | ... | maintained / abandoned / beta |

3. **Pick one.** State why. If 2+ are credible, build quick variants within the spike.
4. **Skip research** for pure logic with no external dependencies.

Use Hermes tools for the research step:

- `web_search("python websocket streaming libraries 2025")` — find candidates
- `web_extract(urls=["https://websockets.readthedocs.io/..."])` — read the actual docs (returns markdown)
- `terminal("pip show websockets | grep Version")` — check what's installed in the project's venv

For libraries without docs pages, clone and read their `README.md` / `examples/` via `read_file`. Context7 MCP (if the user has it configured) is also a good source — `mcp_*_resolve-library-id` then `mcp_*_query-docs`.

### 4. Build

One directory per spike. Keep it standalone.

```
spikes/
├── 001-websocket-streaming/
│   ├── README.md
│   └── main.py
├── 002a-pdf-parse-pdfjs/
│   ├── README.md
│   └── parse.js
└── 002b-pdf-parse-camelot/
    ├── README.md
    └── parse.py
```

**Bias toward something the user can interact with.** Spikes fail when the only output is a log line that says "it works." The user wants to *feel* the spike working. Default choices, in order of preference:

1. A runnable CLI that takes input and prints observable output
2. A minimal HTML page that demonstrates the behavior
3. A small web server with one endpoint
4. A unit test that exercises the question with recognizable assertions

#### Modo UI (variações visuais)

Quando a pergunta é de **design de interface** ("o que deveria aparecer aqui?", "qual layout funciona melhor?"):

1. Gere **2-4 variações radicalmente diferentes** da mesma interface
2. Disponibilize via URL search param ou bottom bar flutuante pra alternar entre elas
3. Cada variação testa uma hipótese de design diferente
4. **Não se preocupe com polimento** — o objetivo é comparar abordagens, não entregar pixel perfect

**Depth over speed.** Never declare "it works" after one happy-path run. Test edge cases. Follow surprising findings. The verdict is only trustworthy when the investigation was honest.

**Avoid** unless the spike specifically requires it: complex package management, build tools/bundlers, Docker, env files, config systems. Hardcode everything — it's a spike.

**Building one spike** — a typical tool sequence:

```
terminal("mkdir -p spikes/001-websocket-streaming")
write_file("spikes/001-websocket-streaming/README.md", "# 001: websocket-streaming\n\n...")
write_file("spikes/001-websocket-streaming/main.py", "...")
terminal("cd spikes/001-websocket-streaming && python3 main.py")
# Observe output, iterate.
```

**Parallel comparison spikes (002a / 002b) — delegate.** When two approaches can run in parallel and both need real engineering (not 10-line prototypes), fan out with `delegate_task`:

```
delegate_task(tasks=[
    {"goal": "Build 002a-pdf-parse-pdfjs: ...", "toolsets": ["terminal", "file", "web"]},
    {"goal": "Build 002b-pdf-parse-camelot: ...", "toolsets": ["terminal", "file", "web"]},
])
```

Each subagent returns its own verdict; you write the head-to-head.

### 5. Verdict

Each spike's `README.md` closes with:

```markdown
## Verdict: VALIDATED | PARTIAL | INVALIDATED

### What worked
- ...

### What didn't
- ...

### Surprises
- ...

### Recommendation for the real build
- ...
```

**VALIDATED** = the core question was answered yes, with evidence.
**PARTIAL** = it works under constraints X, Y, Z — document them.
**INVALIDATED** = doesn't work, for this reason. This is a successful spike.

## Comparison spikes

When two approaches answer the same question (002a / 002b), build them **back to back**, then do a head-to-head comparison at the end:

```markdown
## Head-to-head: pdfjs vs camelot

| Dimension | pdfjs (002a) | camelot (002b) |
|-----------|--------------|----------------|
| Extraction quality | 9/10 structured | 7/10 table-only |
| Setup complexity | npm install, 1 line | pip + ghostscript |
| Perf on 100-page PDF | 3s | 18s |
| Handles rotated text | no | yes |

**Winner:** pdfjs for our use case. Camelot if we need table-first extraction later.
```

## Frontier mode (picking what to spike next)

If spikes already exist and the user says "what should I spike next?", walk the existing directories and look for:

- **Integration risks** — two validated spikes that touch the same resource but were tested independently
- **Data handoffs** — spike A's output was assumed compatible with spike B's input; never proven
- **Gaps in the vision** — capabilities assumed but unproven
- **Alternative approaches** — different angles for PARTIAL or INVALIDATED spikes

Propose 2-4 candidates as Given/When/Then. Let the user pick.

## Regras do Prototype (throwaway)

Independente do modo (spike completo ou quick prototype), estas regras sempre valem:

1. **Throwaway desde o início.** Nomeie o código pra que qualquer um veja que é prototype, não produção
2. **Um comando pra rodar.** O usuário deve conseguir executar sem pensar
3. **Sem persistência.** Estado vive em memória. Só persista se a pergunta do spike for especificamente sobre persistência
4. **Sem polimento.** Sem testes, sem tratamento de erro além do mínimo pra rodar, sem abstrações
5. **Superfície o estado.** Após cada ação, mostre o estado completo relevante pra que o usuário veja o que mudou
6. **Capture quando pronto.** Decisão validada → implementa no código real. O prototype vira branch descartável. O veredito fica no README.md

## Output

- Create `spikes/` (or `.planning/spikes/` if the user is using GSD conventions) in the repo root
- One dir per spike: `NNN-descriptive-name/`
- `README.md` per spike captures question, approach, results, verdict
- Keep the code throwaway — a spike that takes 2 days to "clean up for production" was a bad spike

## Attribution

Adapted from the GSD (Get Shit Done) project's `/gsd-spike` workflow — MIT © 2025 Lex Christopherson ([gsd-build/get-shit-done](https://github.com/gsd-build/get-shit-done)). The full GSD system offers persistent spike state, MANIFEST tracking, and integration with a broader spec-driven development pipeline; install with `npx get-shit-done-cc --hermes --global`.
