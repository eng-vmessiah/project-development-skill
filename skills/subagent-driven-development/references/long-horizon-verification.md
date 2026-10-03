# Long-Horizon Plan Verification

Use this reference for multi-wave plans that add persistence, orchestration, concurrency, CLI, or release gates.

## Evidence discipline

1. Treat every subagent report as a hypothesis, not proof. Re-run the claimed focused test, full suite, compile/type checks, diff check, and any required checker in the parent workspace.
2. When subagents run concurrently, later reports can describe different snapshots. Always run one fresh final suite after all writers stop; never combine intermediate test counts into a final claim.
3. Reviewers must probe the real integration seam, not only fakes: durable Store commit, lease removal/fencing, event append, retry/reclaim, rerun/idempotency, and status/read-only behavior.
4. A full test pass is necessary but not sufficient. Add adversarial probes for failure after terminal commit, event persistence failure, cancellation while a worker is running, malformed manifests, symlinks, and stale/forged snapshots.

## Ownership and parallel waves

- Parallelize only disjoint files and dependencies. If a review finds a cross-module security issue, create a bounded hotfix task with explicit ownership rather than silently editing another task's files.
- Preserve a task's exact Create/Exact/Allowed path contract. Review generated docs and checkers for duplicate Create ownership and stale "not implemented" claims.
- A task is complete only after implementation, spec review, quality/security review, remediation, and fresh re-review. Update the checklist only at that point.

## Durable orchestration invariants

For a V2 execution path, verify all of these against a real store:

- reconciliation is mandatory before claims;
- the same canonical plan hash is used by parser, orchestrator, and Store;
- terminal commit is authoritative;
- event-append failure cannot reclassify or recommit a task whose terminal commit succeeded;
- failed/cancelled work cannot be reclaimed forever;
- retry count is bounded and persisted;
- old lease tokens are fenced after renew/generation changes;
- rerun with an existing run ID is idempotent and does not duplicate evidence/events;
- read-only status does not create directories, locks, or snapshots.

## Concurrency invariants

- Test multiple scheduler instances/processes, not only threads in one object.
- Prove `max_parallel` atomically under race and prevent completed tasks from being reclaimed.
- Cancellation must return promptly; non-cooperative workers must poison/isolate the executor so later runs do not create unbounded live pools.
- Compare randomized completion permutations using a documented normalized projection that excludes volatile lease IDs/timestamps.

## Documentation and human gates

- Evidence packs must distinguish historical/intermediate counts from fresh current results.
- Verify every artifact path exists before calling it evidence; mark absent artifacts as planned/not present.
- Never claim human approval, G6 PASS, release readiness, or authorization from an agent-generated gate.
- A checker itself needs adversarial tests: symlinked root/documents, traversal, broken links/anchors, mixed Create/non-Create declarations, duplicate ownership, malformed root, deterministic output, and exit codes.
- Keep the final state honest: `NOT READY / PARTIAL` is a valid outcome when implementation is complete but human approval or runtime sandbox/provider gates are pending.
