# Fleet Supervisor/Handoff Closeout Reference

Reusable detail for supervised Fleet slices that add handoff artifacts, local persistence, or read-only CLI inspection.

## Wave sequence

1. **S5A — contract hardening:** redaction, numeric/text bounds, nested immutability, hostile-content rejection.
2. **S5B — identity hardening:** typed reasons, complete lineage, ownership/epoch, intervention proposals, diagnosis taxonomy.
3. **S5C — persistence seam:** separate `HandoffStore`; atomic JSON, checksum, idempotent replay, conflict rejection, lock, owner validation, no-side-effect load.
4. **S5D/S5E — exposure hardening:** safe identifiers, bounded safety/refs, complete snapshot/report lineage, immutable detached reports, symlink boundary.
5. **S6 — CLI read-only:** status and handoff preview; deterministic JSON/text; no `STATE` mutation.
6. **S7 — contract review:** map every requirement to code/tests/evidence; treat residual deferred scope separately.
7. **S8 — adversarial grill:** attack iterators, nested redaction, secret-like IDs, paths/PIDs/handles, replay/collisions, stale ownership, symlinks/TOCTOU, parser/completion compatibility, and accidental dispatch.
8. **S8R — remediation:** fix confirmed blockers before closeout; do not carry review bugs into the next branch.
9. **S9 — fresh closeout:** rerun focused/full/deep/static checks and real CLI probes; classify the slice honestly.

## High-value adversarial probes

### Bounded iterators

Never validate an arbitrary iterable with `tuple(values)` first. A hostile or infinite iterator can consume memory or hang before the limit is checked. Consume at most `MAX_ITEMS + 1`; reject on the extra item. Test both a large finite iterator and a generator that would continue forever.

### Identifier secret bypasses

Secret filters must cover assignment separators beyond `=`: `token:VALUE`, `secret:VALUE`, `password:VALUE`, `credential:VALUE`, `api_key:VALUE`, and whitespace variants. IDs are serialized text and need the same policy as summaries, not a weaker identifier-only regex.

### CLI raw-state exposure

Do not serialize arbitrary persisted `fleet_state` into a new supervisor report. Project a bounded allowlist of known fields, recursively redact strings, omit unsafe keys (`debug`, `password`, `token`, `pid`, `path`, `process`, `handle`), and suppress or relativize absolute plan paths. Preserve legacy command behavior only when the new command has its own safe projection.

### Local path boundary

Reject traversal and symlink components in root/run/record paths, including existing ancestral components. A final-component check does not stop `root/link/sub` from resolving outside the intended root. Keep `load(create=False)` side-effect free. Document that cooperative local locks are not distributed leases and do not close the multi-host/TOCTOU threat model.

### Immutability and lineage

Frozen dataclasses do not make nested mappings/lists immutable. Copy and freeze/detach recursively at construction and return detached structures from `to_dict()`. Assert full `Mission → MissionRun → Lane → Attempt → Session` lineage in artifacts, health snapshots, and reports; include owner epoch when it controls authority.

## Closeout evidence template

Record exact, fresh evidence:

```text
focused tests: <count>
full suite: <count>
deep plan validation: <x/y>
compile/static checks: PASS/FAIL
diff check: PASS/FAIL
CLI STATE bytes + mtimes: unchanged/changed
missing-store read: no side effect/side effect
JSON determinism: PASS/FAIL
runtime sentinels: no provider/network/process/dispatch or list findings
```

Classify each requirement as `implemented`, `verified`, `review pending`, `deferred`, `documentation debt`, or `blocked`. A local/read-only slice may be closed when its own evidence is fresh even while provider/live-worker/event-broker/GraphQL/daemon/restart/reassign work remains explicitly deferred. Never call that global feature completion.

## Branch boundary

After S9 closeout, preserve the feature branch's WIP and open a new branch for the next architectural wave. Typical next waves are lifecycle/event/checkpoint integration or orchestration-V2 gates. Do not start the adjacent wave in the closed feature branch, and do not commit/push/merge without explicit delivery authorization.
