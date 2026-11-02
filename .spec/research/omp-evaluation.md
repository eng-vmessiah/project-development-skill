# Research input — oh-my-pi (omp), OMH, TTSR, advisor (avaliado 2026-10-09)

> **Status:** input de discovery, não compromisso. Nada aqui está instalado, integrado,
> agendado ou é fonte de verdade. Migrou do `ROADMAP.md` em 2026-11-02 porque roadmap público
> não é lugar de anotação de pesquisa.

## O que foi observado

Reference input only (same standing as OMH): [oh-my-pi](https://github.com/can1357/oh-my-pi)
(MIT coding harness, Rust+TS; evaluated 2026-10-09). Not installed, not integrated, not
authoritative; nothing here activates a runtime or adapter. Caveats: young project with very
fast releases (pin versions if ever tried) and a wide execution surface (sandbox discipline
required).

**Mapping:** items 1–2 are discovery inputs for the next PD Fleet **Supervisor/control-plane**
increment (the current increment is a read-only observer; steering is the next step) — they
migrate into that increment's `.spec` when it is opened, per the standard PD flow. Stream-rule
guardrails map to bridge gates; the advisor maps to council patterns; metaharness/pi-iso map to
Mission Control and worktree isolation; the optional lane maps to the runtime-adapter boundary. The control-plane increment is expected to surface **visually** — Board tabs
(`pds`/`fleet`/`mc`) live widgets plus the war-room frontend, with actions through the
existing board connector / tool-mode pattern — not only as CLI state. Tracked as `.spec/pd-fleet-control-plane-v1/` (opened 2026-10-09).

- [ ] **Agent Hub ↔ Fleet observer/TUI delta** — feature-by-feature comparison (per-worker
  status/cost/time, live transcript, steer/revive/kill without aborting the parent) against
  the B15 wire/observer/canary surface; feeds the next fleet-TUI phase.
- [ ] **Typed, addressable worker results** — evaluate `agent://<id>/<path>`-style addressing
  plus schema-validated yields as a contract pattern for observer transport and handoffs.
- [ ] **Stream-rule guardrails (TTSR)** — evaluate abort → inject rule → retry-from-the-same-
  point stream rules as a bridge gate mechanism without per-turn context tax.
- [ ] **Advisor-model pattern** — a second model watching every turn on its own context;
  compare with the council/sparring patterns already in use.
- [ ] **Benchmark harness and reflink isolation** — compare metaharness (runners, REST/SSE,
  dashboard) against Mission Control / plan-cockpit; compare reflink-based isolation (pi-iso)
  against current worktree techniques.
- [ ] **(Optional) omp as candidate worker lane** — bounded comparative trial with the same
  provider/model before any adapter work; any activation follows the runtime-adapter boundary
  above and requires separate scope plus explicit approval.
