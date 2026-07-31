# PD Fleet → Hermes Adapter v0 — State

- **Status:** `passed_local_fake_only` / `NOT_READY_RUNTIME`
- **Plan:** `pd-fleet-hermes-adapter-v0`
- **Current gate:** `G3_passed_local_fake_only` — fake-only vertical, independent harness, adversarial checks, and fresh reviews passed
- **Owner/orchestrator:** `isis`
- **Baseline:** local tree after `pd-fleet-scope-alignment` Gate B (`LOCAL_VERIFIED`)
- **Scope authorization:** Vitor selected option 2 on 2026-07-28
- **External effects:** disabled

## Waves

| Wave | Status | Purpose |
|---|---|---|
| W0 Contract discovery | `completed` | inventory seams and define parseable fixtures |
| W1 Fake runtime contract | `completed_local` | in-memory fake-only lifecycle |
| W2 Local fake verification | `completed_partial` | vertical slice, adversarial probes, evidence |

## Gates

| Gate | Status | Meaning |
|---|---|---|
| G0 | `completed` | scope, seam inventory, lineage mapping, normative fixture bundle recorded |
| G1 | `passed_local` | contrato/schema/fixtures passaram duas revisões independentes; sem HIGH/BLOCKER |
| G2 | `passed_local_fake_authorized` | fake-only implementation authorized and locally exercised |
| G3 | `passed_local_fake_only` | vertical/harness/reviews pass; runtime/provider/release remain out of scope |

## Safety boundary

No live Hermes dispatch, provider, network, credentials, cron, gateway, subprocess, OMH, production sandbox, deployment, merge, push, release, or restart is authorized by this scope.

## G1 review result

Two independent read-only reviews returned `HOLD`.

### BLOCKER/HIGH items to close before fixtures are accepted

- Contract discovery was incomplete when the first review ran; G0.1 is now recorded in `CONTEXT.md`.
- Existing `runtime_adapter.py` and `runtime_adapters.py` seams were not reconciled; v0 is now explicitly separate and fake-only, with no import/reachability in the fake wave.
- Owner/lineage fencing must be represented as complete per-operation input, including run/task/attempt/session/workspace, owner and expected lease generation.
- Idempotency scope, request fingerprint, concurrent reservation, replay status and retention must be fixture-normative.
- No-dispatch needs import/capability allowlist and forbidden-reachability evidence, not only `dispatch_count` prose.
- Bounds, redaction order, recursive hostile-input behavior, handoff/evidence schemas and stable errors must be fixture-normative.
- Lifecycle/cancellation/cleanup transitions must be complete and mapped to existing Fleet lifecycle.

### G1 re-review result — HOLD

A segunda rodada de duas revisões independentes também retornou `HOLD`.

Outstanding HIGH findings:

- falta fixture normativa para `stale_generation`, `stale_handle`, lineage/workspace mismatch e fencing concorrente;
- replay same-key/same-fingerprint, `replay_in_progress`, reserva atômica, retenção e invariantes de contadores ainda não estão representados;
- faltam schemas/fixtures operacionais para `observe`, `cancel`, `handoff` e `cleanup`, incluindo confirmação de cancelamento e falha de cleanup;
- redaction-before-canonicalization/hash/storage/evidence ainda não tem algoritmo, domínio, precedência ou evidência;
- no-dispatch ainda não tem allowlist/denylist e prova de reachability/import boundary;
- faltam casos executáveis para ciclos, mappings hostis, números não finitos, controles, unknown fields aninhados, bytes UTF-8 e paths/workspace perigosos.

### Current decision

`g1_passed_local`: a rodada final de duas revisões independentes passou sem BLOCKER/HIGH. O contrato request/result, manifest e fixtures positivas foram validados localmente; G2 continua bloqueado porque a autorização para implementar o fake runtime ainda não foi concedida.

Evidência fresca local: manifest referencia 25 fixtures existentes; JSON Schema de requests/results é estruturalmente válido; projections positivas e cinco result fixtures validam; probes adversariais de null handle, observe array, cancelamento, cleanup, unknown fields, controles, traversal e fingerprint passaram; checker documental reporta 0 violações; `git diff --check` passa. O resíduo MEDIUM de sanitização semântica de `HandoffArtifact.status/next_action` fica explicitamente reservado ao validator fake G2/G3.

## Re-review result — PASS

- **Spec/compliance reviewer:** `passed=true`, sem findings.
- **Security/quality reviewer:** `passed=true`, sem BLOCKER/HIGH; 1 MEDIUM deferred de sanitização semântica de campos bounded.
- **Parent verification:** confirmou os schemas, fixtures, probes, checker e diff-check no workspace corrente.

As revisões históricas `HOLD` permanecem registradas acima como histórico da wave anterior; não representam o estado atual.

## Remediation waves

- **Wave 1:** corrigiu composição do request schema, adicionou `result-schema.json`, result fixtures, bindings, cleanup policy, fingerprints, observe handle e lifecycle cleanup ortogonal.
- **Wave 2:** corrigiu `PrepareResult`, `observe → HarnessEvent[]`, handle não nulo em execute, invariantes bidirecionais de cancel/cleanup e domínio NUL reproduzível da fixture de redaction.

G1 está fechado localmente. A prova executável de no-dispatch, fencing semântico, replay atômico, ciclos/mappings hostis e redaction efetiva permanece deliberadamente em G2/G3.

## G2 implementation checkpoint — F1.1

- **Status:** `g2_f1_1_local_verified_partial`
- **Files:** `scripts/pd_fleet/fake_adapter.py`, `tests/fleet/test_v2_fake_adapter.py`
- **Scope:** deterministic in-memory fake only; no runner/provider/Hermes/network/subprocess/filesystem capability.
- **Fresh evidence:** focused fake + existing runtime adapter tests `50 passed`; full repository suite `1076 passed`; `python -m compileall -q scripts/pd_fleet/fake_adapter.py`; `git diff --check`; documentation checker `violation_count=0`; AST import boundary reports no forbidden imports.
- **Behavior covered:** prepare/no-dispatch, execute/fake result normalization, observe read-only bounded events, cancellation confirmation, bounded handoff, orthogonal/idempotent cleanup, owner/lineage/generation/handle fencing, unknown fields, workspace/payload hostile cases, idempotency conflict, failed cleanup retry, and terminal outcome distinction.

F1.1 is locally verified but does not close G2 or G3. F1.2/F1.3 remain required for concurrent replay reservation, full fingerprint/redaction semantics, recursive hostile values, non-finite/cyclic inputs, and adversarial cleanup/recovery evidence.

## G2 hardening checkpoint — F1.2/F1.3 locally verified

- Added explicit store-lock boundaries for `prepare`, `cancel`, `handoff`, and `cleanup`; `execute` keeps its reservation/effect fences under the same lock discipline.
- Added concurrent probes for cancel/cancel, cleanup/cleanup, handoff/cleanup, and prepare/prepare. Same-key terminal replay is retained with explicit tombstone accounting.
- Expanded recursive redaction before canonicalization to cover URLs, absolute POSIX/Windows paths, authorization/bearer values, and credential assignments.
- Added independent validation of every emitted result category against `contracts/result-schema.json`, including success/failure/timeout, confirmed cancellation, and failed cleanup.
- Fresh evidence: focused fake suite `28 passed`; full repository suite `1092 passed`; compileall, diff-check, documentation checker, and AST no-dispatch checks passed.

F1.2/F1.3 are locally verified. G3 remains blocked until the complete vertical fake-only runner, independent schema/fixture harness, and fresh spec/security reviews are executed.

## Current decision

`g2_authorized_in_progress`: user authorization was recorded before implementation. The fake-only seam has a verified second slice; no live runtime or external effect is authorized.

## G3 verification checkpoint — local fake-only partial

- Added `scripts/pd_fleet/fixture_harness.py`, independently validating all 25 manifest fixtures and separating request projections, result fixtures, and scenario-only metadata.
- Added `scripts/pd_fleet/run_fake_vertical.py`, proving happy lifecycle, confirmed cancellation, cleanup failure/retry, bounded evidence, result-schema validation, and no-dispatch counters.
- Historical evidence before closure: focused `146 passed`; full suite `1101 passed`. Current closure evidence is recorded below.
- `VERIFICATION.md` records the exact commands and scope.

Current decision: `passed_local_fake_only` / `NOT_READY_RUNTIME`. The fake-only local evidence and independent reviews passed. This does not imply Hermes/provider/runtime, human, merge, deploy, or release readiness. The former LOW debts are closed in the G3 closure checkpoint below.

## G3 closure checkpoint

- Closed the descriptor-pinned bundle-read debt in `fixture_harness.py`.
- Closed the alternate module-execution import debt in `run_fake_vertical.py`.
- Fresh closure regression: `3 passed`; full suite `1104 passed`; focused closure/adapter/contract/docs `149 passed`; harness `25/25 valid`; vertical `4 cases`, `local_fake_only=true`, dispatch `[1,0,1,1]`; docs checker `violation_count=0`; direct and module runner reports are byte-identical; compileall, AST parse, and diff-check passed.
- G3 is complete as `passed_local_fake_only` / `NOT_READY_RUNTIME`.

## Resume

There is no remaining implementation work inside the authorized fake-only G3 scope. Any next wave would require a new explicit scope authorization for Hermes/provider/runtime integration. Do not activate live Hermes/provider capability under the current scope.
