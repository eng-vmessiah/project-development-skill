# Plan — porting the benchmark's gaps

Sequenced by risk, not by novelty. Each wave is independently shippable and independently
verifiable; none of them requires a UI.

## P0 — Effect reconciliation (ISIS core) · M

The only gap that changes safety.

- `tool.effect_unknown` and `effect.reconciled` join `EVENT_TYPES`.
- A tool call that completes without a receipt or result proof emits `tool.effect_unknown` with
  `payload_hash`, `lineage` (parent run/session), `operation`.
- Verdict artifact: `evidence/<mission>/reconciliations/<event_id>.json`
  (`decision: executed|not_executed`, `by`, `at`, `payload_hash`, `note`).
- CLI: `isis reconcile list --mission <id>` and `isis reconcile decide <event_id> --executed|--not`.
- Invariant: no code path may turn `unknown` into `success` silently.

**Acceptance:** a fixture tool that returns nothing produces `tool.effect_unknown`; `isis mission show`
lists it; a verdict appends `effect.reconciled` and closes it; suite proves that unknown never
auto-resolves.

## P1 — Mission route / investigation mode · S

- `route: investigation | implementation | hybrid` on the mission.
- Investigation: no dispatch, no lease, no worker; requires `spike.completed` + `review.completed`
  before `mission.closed`.
- Closing an investigation mission without those events is refused (fail-closed).

**Acceptance:** an investigation mission reaches `mission.closed` with **zero** `run.*` events and
with spike/review artifacts; an implementation mission without approval still refuses.

## P2 — Execution tree projection · M

- `isis mission tree --mission <id> [--json]`, derived **only** from `events.jsonl`.
- Nodes: mission -> task -> attempt -> session -> worker -> tool; empty parents render as
  `sem sessao` / `sem worker` nodes, never omitted.
- Any node that cannot be traced to an event is a bug, not a placeholder.

**Acceptance:** node count reconciles with event count for the same mission; deleting an event
removes its node; a golden fixture covers a two-attempt retry and a delegated subagent.

## P3 — Context ledger · M

- `.spec/<mission>/CONTEXT.md` with five sections: facts, decisions, assumptions, constraints, open
  questions; each entry carries provenance and an ID.
- Counters in `isis mission show`; version bump + `plan.versioned`-style event on change.

**Acceptance:** counters equal the file's entries; editing bumps the version; an empty section is
preserved as an explicit empty state.

## P4 — Artifact metadata · S

- `sensitivity` (`internal|public|secret`) and `version` in the evidence manifest; `artifact.produced`
  carries `sha256`, `kind`, `sensitivity`.

**Acceptance:** manifest round-trips; a missing sensitivity defaults to the most restrictive value,
never to `public`.

## Non-goals

No new cockpit UI. No login/SSO. No Jira/n8n integration. No clone of the demo HTML. No copy of any
third-party visual identity or copy. No change to product branding.

## Ordering rationale

P0 first because it closes the only *safety* hole; P1 second because it is cheapest and pays back in
budget; P2/P3/P4 can follow in any order and each is independently useful.
