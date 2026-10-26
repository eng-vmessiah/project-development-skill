# Gap analysis — PD Fleet + ISIS core vs the benchmark

**Method:** read/grep of `scripts/pd_fleet/*.py` (17,635 lines, 30 modules) and
`core/isis_core/*.py`; each row cites what was actually found, not what was assumed.

## Summary

| # | Capability | BTG | PD Fleet | ISIS core | Verdict | Size |
|---|---|---|---|---|---|---|
| 1 | Effect reconciliation (unknown effect -> human verdict) | yes | `Orchestrator.reconcile()` is **state** reconciliation (plan vs lifecycle), fail-closed and side-effect free; no tool-effect concept | guard blocks by path; `tool.used` is recorded; no unknown/verdict state | **real gap** | M |
| 2 | Route / mission mode (investigation closes without dispatch) | yes | none | none: every mission dispatches | **real gap** | S |
| 3 | Execution tree projection | yes | `attempt` exists in `dispatch.py`; no tree | events carry `parent_run_id`, `depth`, `subagent.*`, `tool.used`; **no view** | data exists, view missing | M |
| 4 | Context ledger (facts/decisions/assumptions/constraints/open questions, counted, versioned) | yes | free-form `CONTEXT.md` | none | partial | M |
| 5 | Artifact metadata: sha256 + age + sensitivity + version | yes | `EvidenceRecord.sha256` | `evidence/<mi>/` + `SHA256SUMS` + `manifest.json` | ~70% done | S |
| 6 | Event taxonomy `<entity>.<verb>` with source | 7 of 85 visible | own event log | **34 types**, incl. `gate.*`, `artifact.*`, `tool.used`, `budget.exceeded` | mostly covered | S |
| 7 | Provider capability matrix (declared per operation, per session) | yes | `capabilities` is a *task* field (`list[str]`), no provider matrix | model/provider routing only | **real gap** | M |
| 8 | Scope gate (`GATE-SCOPE`) | yes | `GateType`: review, grill, smoke_test, evidence | generic gates | small gap | S |
| 9 | Honest empty states | yes | documented in `docs/PLAN-COCKPIT.md` | CLI only (no UI) | covered by rule | - |
| 10 | Plan before runtime | yes | yes (`plan.yaml` + gates) | dispatch required to produce anything | covered | - |

## What is *not* a gap (do not rebuild)

Gates with human decisions (`pd_fleet.gates.HumanDecision`), checkpoints with lifecycle snapshots,
dispatch with attempts and retry policy, hashed evidence, event log with size/payload caps, budget
ceiling with fail-closed refusal. These already exist and are stronger than the demo.

## The three gaps worth money

**1. Effect reconciliation.** This is the only capability in the benchmark that no local component
has, and it guards the failure mode that matters most: a tool that ran, did *something*, and cannot
prove it. Today the guard decides *before* execution (path scope) and evidence seals *after*
success; nothing represents "executed, effect unknown".

**2. Route / investigation mode.** Today a read-only investigation pays for a dispatch, a worker and
a lease. The benchmark's rule — investigation concludes with spike + review + analytical conclusion,
archive, no worker — is a direct cost and risk reduction, and it is a small change.

**3. Execution-tree projection.** The data already exists in `events.jsonl` (lineage, attempts,
sessions, tool calls). What is missing is a derivation that the UI layer can bind to. Without it
every cockpit rewrite re-invents the tree by hand — which is exactly how telemetry gets fabricated.

## Honest limits of this analysis

- The benchmark is a **demo with fixture data**; no production behaviour, latency or failure mode was
  observed. Nothing here is evidence about how the real product behaves under load.
- Two screens (conclusion, providers) are partially illegible; field names in row 8 are `inferred`.
- `reconcile()` in `orchestrator.py` was read at the docstring and the first 20 lines; it may cover
  more than state reconciliation. Row 1 should be re-verified before implementation.
