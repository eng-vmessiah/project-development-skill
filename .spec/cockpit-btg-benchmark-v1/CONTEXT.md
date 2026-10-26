# Context — why this spec exists and what it is not

## Decisions

1. **Benchmark, not backlog.** The source is an internal product observed through a phone recording
   of a monitor. It is treated as evidence of *patterns*, never as a requirements document. Nothing
   here is copied: no code, no copy, no layout, no branding.
2. **No fifth cockpit.** Locally there are already four overlapping surfaces: `pd_fleet` +
   `PLAN-COCKPIT` + `plan_cockpit_sync` (PD), the `isis-cockpit` skill, the Hermes Kanban, and the
   `isis` core (missions/events/evidence/cost). The gap is a **projection contract**, not another UI.
   Building a new cockpit would be debt with a demo attached.
3. **Gaps are defined by what exists**, not by what is missing in the benchmark. Every "gap" row in
   `GAP.md` cites the local file that fails to provide the capability.
4. **The conclusion screen is quarantined.** Two independent reads of the same frame disagree on the
   percentages (`71%` vs `77%`) and on a label (`Renegociação` vs `Recuperação`). Numbers from that
   screen are not usable as fact, and the source analysis presenting them as confirmed is a defect
   worth remembering: OCR read twice is still OCR.
5. **Material stays private.** The recording shows a corporate e-mail, intranet URL and internal
   workspace names. Frames remain in the Obsidian vault; the browser chrome is cropped before any
   external use. This spec contains no screenshot reference that identifies the company.

## Open questions for the owner

- Is `route: investigation` a real product decision, or should investigations stay a mode of the
  same mission instead of a separate route? (affects P1 shape, not P0)
- Does effect reconciliation apply to *every* tool, or only to tools declared as mutating? (affects
  event volume: `tool.used` today is emitted for all calls)
- Should the execution tree be CLI-only first, or bound directly into the existing `mc` board tab?
