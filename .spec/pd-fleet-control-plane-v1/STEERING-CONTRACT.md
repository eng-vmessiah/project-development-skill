# STEERING-CONTRACT.md — v1 (T-301)

**Status: DESIGN ONLY — zero action surface ships from this document.**

Every verb below is a *contract*, not an endpoint. Implementation is a separate scope with its own
spec, its own gate and its own authorization (SPEC R4). Until that gate passes, the Fleet gateway
capability allowlist stays `CAPABILITIES_V1 = frozenset({"observation"})`
(`scripts/pd_fleet/gateway_deny.py`, `CAPABILITIES_V1`) and no module in this repo may execute a steering command.

Rule zero inherited from the sibling contract: **a command that cannot be proven to have been
applied is reported as not applied** — never as success. Telemetry rule and steering rule are the
same rule: no observation, no claim.

---

## 1. Vocabulary — three planes, deliberately separated

| Plane | Question it answers | Artifact today | May execute? |
|---|---|---|---|
| **Intent** (`.spec`) | what the mission allows | SPEC/PLAN/plan.yaml gates | no |
| **Diagnosis** | what the supervisor *thinks* is wrong | `SupervisorDiagnosis`, `InterventionProposal` (`scripts/pd_fleet/supervision.py`) | **no** — proposals are data |
| **Steering** (this document) | what an operator *requests* be done to a running target | `SteeringCommand` (below) | only through a runtime-owned **sink** |
| **Execution** | the process/agent actually changing behaviour | Hermes session, Codex/OpenCode lane, Orca terminal, fleet runner | yes — and only it |

The control plane **never** kills, pauses or types into anything itself. It emits a signed-by-audit
*request*; the runtime that owns the target either applies it or refuses. This preserves D-002
("Supervisor é control-plane, não executor") and keeps the blast radius inside the runtime that
already holds the process.

Consequence: `InterventionProposal` is **not** upgraded into a command automatically. A proposal is
an input to a human/agent decision; a command is an output of one. The gap between them is where
every audit record lives.

---

## 2. Verbs (v1 contract; five, not four)

SPEC R4 names steer/pause/kill/retry. **`resume` is added and declared** as mission decision **D-006**
(below): a pause verb without an exit is a trap — an operator would be forced to `kill` to undo a
`pause`.

### Decisions introduced by this contract

- **D-006 — `resume` is a first-class verb.** Pause without an exit forces operators into the
  destructive verb. `resume` is scoped to pauses the fleet itself applied (`paused_by` must match
  the caller) and is T1. Mirrored into `CONTEXT.md` at T-401 closeout.
- **D-007 — a verb's effect is observed through the sink's health snapshot first, the R1 bus
  second.** `ACTIVITY-CONTRACT.md` defines `kind:status` as `running|waiting|done|failed|blocked`:
  it has no `paused`, `cancelling` or `cancelled`, so the bus alone cannot prove a pause or a kill.
  `observed_state` therefore comes from the sink's process-level evidence (the `liveness` /
  `readiness` / `progress` signals already modelled in `supervision.py`) plus, where the runtime
  echoes `command_id` in the event `meta`, the R1 stream. Extending the R1 status enum is a v2
  requirement (§11.7) — v1 does not pretend to have it.

| verb | intent | target | preconditions | effect boundary | idempotency | tier |
|---|---|---|---|---|---|---|
| `steer` | change what the agent does next, without restarting it | one live run | target owned by the sink; run not terminal; turn boundary reached | text ≤ 2000 chars, no paths, no secrets, no shell; delivered as a *message*, never as keystrokes into a PTY | `key` = (verb,target,text-hash,epoch) | **T1** |
| `pause` | stop after the current turn; keep transcript and worktree | one live run | run `running`; cooperative runtime | turn-boundary stop only. **`SIGSTOP` is forbidden** (wedges the runtime, loses the transcript, cannot be audited) | (verb,target,epoch) | **T1** |
| `resume` | undo a pause **we** applied | paused run | audit record shows `paused_by == <caller>`; not human-paused | may not resume a session a human paused outside the fleet | (verb,target,epoch) | **T1** |
| `kill` | end a run and its process group | one live run | sink owns the process (PGID recorded at spawn) | `SIGTERM` → grace (default 10 s, ≤ 60 s) → `SIGKILL`; group only, never a wildcard | (verb,target,epoch,nonce) | **T2** |
| `retry` | re-execute a terminal attempt as a new attempt | terminal run | previous attempt terminal; `attempt < retry_policy.max_attempts`; error class in `retryable_errors` | new attempt id, same task contract; **never** retries over a dirty worktree without a recorded snapshot ref | (verb,target,attempt) | **T3** when the task has side effects, else **T2** |

Notes that are contract, not preference:

- **`steer` is a hint, not an instruction override.** The runtime may apply it at the next turn
  boundary and the agent may ignore it; the audit records `applied` (delivered to the runtime) and
  separately `observed` (the agent's next event shows the effect, or does not).
- **No `SIGSTOP`/`SIGCONT`, no PTY injection, no file mutation** as a steering mechanism. A verb
  whose effect cannot be observed in the activity stream (R1) is out of contract.
- **`kill` is a last resort, not a timeout.** The run-level timeout path already exists
  (`scripts/pd_fleet/parallel.py:100-214`: `cancel_event`, `cancelled`/`timeout`, pool fencing).
  Steering `kill` targets a *live* run the parallel runner does not own; it must not be used as a
  substitute for that mechanism.

---

## 3. Target ownership — owned vs attached

The single most important safety distinction in this contract.

| relation | how it arises | allowed verbs | rationale |
|---|---|---|---|
| **owned** | the fleet runner spawned the process; PGID, worktree and run_id are recorded | all five | the sink holds the process handle and can prove what it started |
| **attached** | the observer *sees* a session it did not start (Hermes desktop, gateway, a Codex lane, an Orca terminal) | none in v1; later `steer`/`pause` only if the runtime exposes a cooperative API | an attached target can only be observed. Typing into it, or killing it by pid discovery, is out of contract — it breaks the audit chain (the control plane cannot prove which process family it ended) |

`supervision.py` already carries the lineage that makes this decidable: `mission_run_id`, `task_id`,
`lane_id`, `attempt_id`, `session_id`, `owner_epoch`. **A command without a resolvable lineage ref
is refused** (`outcome: refused`, `reason: no_lineage`).

**Blast radius rules (hard):**

1. One command = one target. No wildcards, no prefixes, no "all lanes".
2. A batch of N commands is N audited records; each is authorized on its own tier.
3. `owner_epoch` is a fencing token: a command carrying a stale epoch is refused
   (`stale_owner_epoch`), reusing the check already implemented for reconcile
   (`scripts/pd_fleet/supervision.py:194-196`).
4. A second command for a target with one in flight is refused with `conflict` — single writer per
   target, no queue, no implicit retry of the command itself.

---

## 4. Command envelope (schema v1)

```json
{
  "v": 1,
  "command_id": "sc-<uuid4>",
  "idempotency_key": "<sha256 hex>",
  "ts": "2026-11-02T12:00:00Z",
  "verb": "steer|pause|resume|kill|retry",
  "target": {"agent_id": "...", "run_id": "...", "mission": "...|null", "task": "T-301|null",
             "lane_id": "...|null", "attempt": 1, "owner_epoch": 7},
  "tier": "T1|T2|T3",
  "reason": "retry|fallback|handoff|replan|human_intervention",
  "payload": {"text": "<=2000 chars (steer)|null", "grace_seconds": 10},
  "evidence_refs": ["snapshot:run:task", "artifact:.spec/.../x.md"],
  "authorization": {"kind": "none|owner_approval", "ref": "...|null", "expires_at": "...|null"},
  "caller": {"agent_id": "...", "session_id": "...", "profile": "..."},
  "nonce": "<one-shot, T2/T3 only>"
}
```

- `reason` reuses `HandoffReason` (`scripts/pd_fleet/handoff.py:39`: retry, fallback, handoff,
  replan, human_intervention) — a new vocabulary would fork the audit between supervision and
  steering.
- **Canonicalization:** JSON with sorted keys, no whitespace, UTF-8; `idempotency_key =
  sha256(canonical({v, verb, target, payload, tier, nonce?}))`. Re-submitting the same key returns
  the stored outcome and does **not** re-execute. This is the same discipline as dispatch's request
  fingerprint (`scripts/pd_fleet/dispatch.py`, the `dispatch()` request-key block).
- **Redaction before persist** (same rule as R1): no secrets, no env values, no prompt text, paths
  workspace-relative or `external:<scheme>`. `payload.text` is truncated at 2000 chars and is the
  only free-text field in the envelope.
- **Validation order:** shape → tier → authorization artifact → lineage → epoch → verb
  preconditions → sink capability. Anything ambiguous denies. Reuse the argument-validation style
  already proved in `dispatch.py` / `contracts.py` (explicit types, bounded strings, no truthiness).

**Outcome record (written by the sink, appended to the audit log):**

```json
{"command_id": "...", "outcome": "applied|refused|unsupported|expired|conflict|timeout",
 "observed_state": "running|paused|terminal|null", "detail": "<bounded, redacted>",
 "ts": "...", "sink": "hermes|fleet|orca|codex-lane", "latency_ms": 42}
```

`applied` means *the runtime accepted the request*. It does not mean the agent obeyed. `observed` is
never inferred: it requires one of the two evidences named in **D-007** — the sink's health snapshot,
or an R1 event whose `meta.command_id` equals this command. Absent either, the record stays `applied`
with `observed_state: null` and **no claim of effect** is made anywhere. Collapsing the two facts is
how "steered" becomes a fabricated claim.

---

## 5. Target state machine

```
                 steer (self-loop, audited)
                        │
   spawned ──► running ─┼──► paused ──► running        (resume: only if paused_by == caller)
                  │     └──► terminal                  (done | failed | blocked | cancelled)
                  │              │
                  │              └──► retry ──► running (attempt+1, new attempt_id)
                  └── kill ──► cancelling ──► cancelled (grace → SIGKILL → pgid empty)
```

Rules:

- `paused` is a *cooperative* state reported by the runtime, never assumed. `supervision.py`
  already models the failure honestly: `desired_state=paused` with `liveness=alive` is
  `degraded/pause_not_observed` (`scripts/pd_fleet/supervision.py`, `reconcile_snapshot`). Steering
  keeps that semantics — an unobserved pause is a **failed** pause, reported as `timeout`, and the
  evidence of failure is the sink's liveness still `alive`, **not** the absence of a bus status
  (R1 v1 has none — D-007).
- `cancelling` is a distinct intermediate state so a kill that does not land is visible; the
  terminal `cancelled` requires the PGID to be empty (proven, not assumed).
- Terminal states are sticky: no verb acts on a terminal target except `retry`, which creates a
  new attempt rather than reopening the old one.

---

## 6. Authorization tiers

| tier | verbs | who may issue | what is required | default |
|---|---|---|---|---|
| **T0** | observation (shipped) | any local reader | — | open |
| **T1** | `steer`, `pause`, `resume` | the mission orchestrator, in-session | lineage + epoch + audit; reversible | **deny** ("deny") |
| **T2** | `kill`, side-effect-free `retry` | orchestrator + explicit owner approval artifact | T1 + approval ref (owner decision recorded, not a boolean) | deny |
| **T3** | `retry` of a task with side effects | owner, per command | T2 + named blast radius + rollback statement | deny |

The gate ladder to reuse is the composite deny of B15b.2: every use passes all eight gates, absence
denies, no inheritance, re-validated per call (`scripts/pd_fleet/gateway_deny.py:1-45`). Steering
adds **one** gate, `B9 = steering_capability_allowlisted`, whose value must be a member of a set
that **does not exist yet** (`{"observation"}` today). Adding a member to that set is the
authorization gate of the future implementation — not a config toggle.

Two rules about approvals, learned from `gates.py`:

- `HumanDecision` is **audit metadata, not authentication** (`scripts/pd_fleet/gates.py`,
  `HumanDecision`). An approval record proves *what a human said*, never *who is typing now*. Local
  callers are trusted only within the local transport boundary (§8).
- An approval is **scoped, expiring and bound to the caller**: it names the command text hash (or the
  verb+target+epoch), `expires_at`, and the `agent_id` + `session_id` that may present it. A valid
  artifact presented by a different session is `refused` — an approval for `kill A` is not an
  approval for `kill B`, and it is not an approval for another agent's `kill A` either. Residual risk
  is stated, not hidden: two sessions of the same agent on the same local profile are
  indistinguishable to this contract, which is why T3 additionally requires the owner's own command
  text (its hash), never a standing flag.

---

## 7. Audit trail

Append-only JSONL, one record per state transition (request, decision, outcome), hash-chained:

```json
{"seq": 12, "ts": "...", "kind": "request|decision|outcome",
 "record": {"...": "envelope or outcome"},
 "prev_hash": "<sha256 of previous line>", "hash": "<sha256(canonical(record)+prev_hash)>"}
```

- **Location** (design): `~/.hermes/fleet/steering/audit-YYYYMM.jsonl`, local only, never rewritten;
  rotation by month, never truncation of a live file. Every line redacted at write time with the R1
  rules — an audit log is a persistence surface, so redaction happens *before* the write, not at
  read time.
- **Chain verification** is a first-class operation: `verify_chain(path)` returns the first broken
  seq. A broken chain is a `failed` audit, and a failed audit blocks further T2/T3 commands
  (fail-closed: no safe log, no destructive verb).
- **What must be in every record:** command_id, verb, tier, target lineage, epoch, caller, reason,
  outcome, latency, sink, evidence refs. **What must never be in it:** prompt/CoT text, env values,
  absolute home paths, tokens, free-form agent output.
- **Retention:** 12 months local, then archival to `.spec/<mission>/audit/` for mission-scoped runs
  (the mission record is the durable one; the live log is operational).
- The audit is the *only* place a command's effect is claimed. Board widgets may render counts from
  it; they may not render a command as applied unless an `outcome: applied` line exists.

---

## 8. Transport & trust boundary

- **Local only.** Unix socket or stdio; no TCP listener, no HTTP, no remote fan-in. This is the same
  posture as the board connector (`scripts/board_connector.py:1-16`: stdio MCP, no network, no
  secrets) and the gateway bridge.
- **Caller identity is a local session record** (`agent_id`, `session_id`, `profile`), recorded but
  not treated as proof. Cross-profile calls require an explicit approval artifact (T2+); a command
  from a profile that does not own the mission is `refused`.
- **No credentials in the envelope, ever** — no tokens for lanes, no SSH, no cloud keys. If a verb
  would need a secret to reach a runtime, that runtime is out of scope for steering (it becomes an
  attached/observe-only target).
- **Everything is bounded**: text ≤ 2000 chars, grace ≤ 60 s, evidence refs ≤ 32, audit line
  ≤ 8192 bytes. Unbounded input is a denial vector even locally.
- **The sandbox is not a network boundary.** `scripts/pd_fleet/sandbox.py` refuses shell
  metacharacters in argv and refuses URLs in **environment values** (`sandbox.py:215`), and it
  redacts URLs from captured output (`sandbox.py:31,90`) — but an exactly-allowlisted argv may
  itself carry a URL and the spawned binary may open a socket. Measured, not assumed:
  `steering/probes/probe_sandbox_refusal.py`. Therefore "no network" is a property of the *sink's
  argv allowlist and environment*, never of the runner. Any future sink must pin argv to commands
  that cannot fetch, or state plainly that it does not.

---

## 9. Refusal, degradation and honesty

| situation | outcome | never |
|---|---|---|
| runtime cannot do the verb (non-cooperative lane) | `unsupported` | silently degrade to kill |
| requested state not observed within the window | `timeout` | report `applied` |
| two commands in flight for one target | `conflict` | queue the second |
| stale epoch / stale approval | `expired` | refresh automatically |
| verb not in allowlist | `refused` | widen the allowlist |
| audit chain broken | `refused` (T2/T3) | write anyway |

A refusal is a **successful contract outcome**: it must be as visible on the surface as an
application. Surfaces show `requested → refused` rather than hiding the attempt.

---

## 10. What exists today (inventory; this contract is grounded on it)

| piece | file | relevance |
|---|---|---|
| composite deny, B1–B8, allowlist `{observation}` | `scripts/pd_fleet/gateway_deny.py` | the gate ladder B9 extends |
| argv-allowlisted process runner, timeouts, bounded output, no shell — **no network isolation** (URLs are refused in `env`, not in `argv`) | `scripts/pd_fleet/sandbox.py:31,90,215` | the only sanctioned way a future sink *may* spawn anything; the network guarantee has to come from the sink's argv |
| default-deny adapters, request fingerprint, dry-run | `scripts/pd_fleet/dispatch.py:458-500` | idempotency + refusal style |
| read-only supervision, proposals, `owner_epoch` fencing | `scripts/pd_fleet/supervision.py` | lineage + `stale_owner_epoch` + honest pause semantics |
| in-process cancellation, pool fencing | `scripts/pd_fleet/parallel.py` | the existing timeout/cancel path steering must not duplicate |
| retry policy (max_attempts/backoff/retryable_errors) | `scripts/pd_fleet/models.py:189-232` | `retry` preconditions |
| human gate types + decision-as-metadata | `scripts/pd_fleet/gates.py` | approval artifacts |
| tool-mode actions by click (3 fixed sync scripts) | `scripts/board_connector.py` | today's only "action" surface: allowlisted scripts, no args beyond an enum |
| activity stream (effect observation) | `scripts/pd_fleet/activity_emit.py` + `plan_cockpit_sync.py` | the only proof a verb had an effect |

**Gap:** there is no command envelope, no audit chain, no sink interface, no capability above
`observation`, and no surface affordance. That is the whole of the future implementation — and the
whole of what this document refuses to build now.

---

## 11. Implementation boundary (what v2 would have to satisfy)

A future implementation is authorized only as a separate mission whose SPEC carries, at minimum:

1. Its own gate ladder, with a **blocking owner gate** before the first T2 verb exists.
2. A `SteeringSink` protocol with at least a fake sink (deterministic, testable) before any real
   runtime sink; the real sink may only act on **owned** targets.
3. Allowlist extension as an explicit, reviewed change to `CAPABILITIES_V1` (B7) — one capability
   per verb, no wildcard capability.
4. Tests: envelope validation (shape/type/bounds), canonicalization determinism, idempotency
   (same key → same outcome, one execution), epoch fencing, refusal matrix, audit chain verify +
   tamper detection, and an anti-fabrication test that a command without an `outcome` line renders
   as `requested`, never `applied`.
5. A rollback statement per verb: what is restored if the verb misfires (transcript retained, worktree
   snapshot ref, cancelled attempt marked `orphaned`, not `failed`).
6. Proof that no new network listener exists, that the sink's argv allowlist carries no
   URL-bearing argument (the runner refuses URLs in `env`, not in `argv` — §14), and that the
   board connector's allowlist is unchanged. This is a **tested gate item**, not a prose promise:
   the §8 sentence "the sink does not fetch" is only allowed to stand if the inspection runs.
7. **One of two R1 amendments**, so pause/kill stop being blind (D-007): either `kind:status` gains
   `paused` / `cancelling` / `cancelled` in `ACTIVITY-CONTRACT.md` (a versioned amendment with
   fixtures), or every sink echoes `command_id` in the next event's `meta` — the audit's `observed`
   field is not allowed to be inferred without one of them.

Until all seven exist, the label for this area stays **`designed, not implemented`** — never
"partially working".

---

## 12. Owner decisions needed before v2 (blocking)

| id | question | why it blocks |
|---|---|---|
| **Q1** | Is `steer` allowed to inject text into a *attached* Hermes session (one the fleet did not spawn), or is attach mode permanently observe-only? | decides whether the largest real-world target set is in scope at all |
| **Q2** | For `kill`: is 10 s SIGTERM grace acceptable, and is a *human* approval required per kill, or a standing approval per mission run? | tier T2 policy; per-command approval is safest but heavy in an incident |
| **Q3** | `retry` over a dirty worktree: v1 already fixed the conservative side (§2 — `never` without a recorded snapshot ref). Is that enough, or do you want an explicit snapshot command as a hard precondition? The answer can only tighten; relaxing it is a different contract revision. | decides the shape of T3's precondition, not whether the guard exists |
| **Q4** | Retention: 12 months local + mission archival, or shorter? | privacy/disk vs auditability |

---

## 13. Review packet — canonical questions

For the independent reviewer (fresh eyes, read-only):

1. Does the contract keep the control plane a **non-executor** end to end, or does any path let a
   command take effect without a runtime-owned sink?
2. Is the **owned vs attached** split sufficient to prevent the classic failure — killing a process
   the control plane cannot prove it started?
3. Is any verb's **effect unobservable** in the R1 activity stream, making `applied` unfalsifiable?
4. Are the **preconditions** for each verb complete (terminal states, attempts, epoch, worktree
   state), or can a verb be issued in a state where it is meaningless?
5. Does the **audit** design actually make claims checkable (hash chain, request/decision/outcome
   separation, redaction-before-write), or is it a log of intentions?
6. Is **tiering** default-deny with approvals that are scoped, expiring and non-transferable?
7. Does anything here contradict SPEC R4, D-002 (read-only first), or the golden rule?
8. Is the **inventory** in §10 accurate against the repo (no invented module, no invented capability)?
9. Is the **boundary in §11** testable, or would a future implementer be able to claim "mostly done"?
10. Are the owner questions in §12 genuinely blocking, or bikesheds that should be decided here?

---

## 14. Grounding evidence (executed, T-301)

This contract's repo claims are not asserted from reading alone. Six probes run against the real
modules and are re-runnable:

```
/usr/bin/python3 .spec/pd-fleet-control-plane-v1/steering/probes/run_probes.py
TOTAL=6 PASS=5 FAIL=1   (the FAIL is the refuted claim below, by design)
```

| claim (§) | probe | real output | verdict |
|---|---|---|---|
| allowlist is exactly `{observation}`; absent gates deny B1–B8; `steer.kill` denied at B7 (§6, §10) | `probe_gate_allowlist.py` | `CAPABILITIES_V1=frozenset({'observation'})`; absent → `allowed=False denied_by=('B1'…'B8')`; `steer.kill` → `denied_by=('B7',)` | CONFIRMED |
| stale `owner_epoch` blocks reconcile (§3.3, §5) | `probe_epoch_fencing.py` | epoch 7 vs active 8 → `status='blocked' reasons=('stale_owner_epoch',)` | CONFIRMED |
| `paused` + `alive` is `degraded/pause_not_observed` (§5) | `probe_pause_semantics.py` | `status='degraded' reasons=('pause_not_observed',)` | CONFIRMED |
| `reason` reuses `HandoffReason` (§4) | `probe_reason_enum.py` | `kill_now` → `SupervisionError: invalid intervention reason`; `retry` stored | CONFIRMED |
| canonicalization is order-independent and payload-sensitive (§4) | `probe_idempotency.py` | identical hex on repeat and reorder; different hex on changed payload | CONFIRMED |
| the runner refuses URLs in argv (§10) | `probe_sandbox_refusal.py` | metacharacter `rejected:argv_invalid`; URL `accepted` | **REFUTED** → §8/§10 corrected above: URLs are refused in `env` and redacted in output, **not** in argv |

**What the grounding does NOT prove** (the honest boundary, from `steering/GROUNDING.md`): steering
does not exist, B9 is not implemented, there is no command lineage/authorization/sink/audit-chain,
idempotency is a formula rather than a persisted store, and the sandbox was never asked to execute
anything — so no claim here is about network isolation at runtime, concurrency or hostile input
beyond the measured cases. Design stays design.

---

## 15. Independent review (T-301, conforming to §13)

`PASS_WITH_RESERVATIONS` — 0 BLOCKER, 1 HIGH, 3 MEDIUM, 2 LOW, 1 NIT. Executed by a reviewer on a
**different model family** from the author (GLM-5.3-Flash via the OpenCode CLI, read-only, in this
worktree), against the 10 canonical questions in §13 and the code cited in §10. Dispositions:

| finding | severity | disposition |
|---|---|---|
| R1-01 — R1 `kind:status` has no `paused`/`cancelling`/`cancelled`, so pause/kill had no proof channel | HIGH | fixed as **D-007** (§2) + §5 + §11.7: effect is proven by the sink's health snapshot, bus echo is a named v2 requirement |
| ST-02 — `D-006` cited but not defined in this mission | MEDIUM | fixed: D-006/D-007 now declared in §2 |
| ST-03 — approval scoped and expiring but not caller-bound | MEDIUM | fixed in §6: artifact names `agent_id`+`session_id`; residual risk (same-profile sessions) stated |
| ST-04 — `observed` for `steer` lacked an operational definition | MEDIUM | fixed in §4: either sink snapshot or `meta.command_id`; otherwise `observed_state: null`, no claim |
| ST-05 — `retry` "never" vs Q3 reopened the same condition | LOW | fixed in §12: Q3 can only tighten |
| ST-06 — line-number citations drifted | LOW | fixed: citations now name symbols (`CAPABILITIES_V1`, `HumanDecision`, `reconcile_snapshot`, `dispatch()` block) |
| ST-07 — "or state plainly that it does not" was an untestable escape hatch | NIT | fixed in §11.6: the network statement is a tested gate item |

The reviewer's explicit limits (not run: `pytest tests/`, `pd validate`, live `state.db`/bus; sandbox
`run()` never called) are unchanged and are the same limits §14 declares.
