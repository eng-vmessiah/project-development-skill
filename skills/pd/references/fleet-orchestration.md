# Fleet Orchestration Reference

Use this reference when a PD goal is large enough to justify a supervised fleet rather than a single linear agent.

## Operating model

Treat the plan as an executable coordination protocol:

```text
raw goal → prompt refinement → discovery/spec → plan compiler → plan grill
→ orchestrator → bounded workers → review/grill → smoke/evidence gate
→ closeout + continuation prompt
```

The orchestrator owns state, dependency release, blockers, retries, and evidence. It should not opportunistically implement source changes that belong to a worker.

## Initial roles

- `orchestrator`: schedule waves, inspect state, pause/replan, consolidate reports
- `researcher`: read-only repository and domain discovery
- `analyst`: requirements, architecture, risk and completeness review
- `coder`: implementation within explicit path ownership
- `test-engineer`: tests and focused validation
- `reviewer`: diff and contract review
- `grill`: adversarial search for hidden assumptions and gaps
- `smoke-tester`: real critical-path execution
- `prompt-refiner`: turn goal/feedback into a reusable execution prompt

Start with these roles; do not create specialists without a demonstrated bottleneck.

## Task contract

Every task should declare:

```yaml
id: T-001
wave: 1
role: coder
objective: observable result
depends_on: []
allowed_paths: []
forbidden_paths: []
inputs: []
outputs: []
acceptance_criteria: []
validation_commands: []
blocked_when: []
status: pending
```

Worker reports must include status, files changed, commands actually run, results, blockers, and residual risks. A worker's claim is not evidence until the orchestrator checks critical artifacts and reruns important commands.

## Wave and parallelism rules

Waves are sequential; independent tasks within a wave may run in parallel. A task is eligible only when dependencies are complete, inputs exist, decisions are closed, and its write paths do not conflict with another running task. Separate worktrees or explicit path ownership are required for parallel writers.

Use gates:

1. intake: operational goal, scope, constraints and definition of done;
2. discovery/spec: repository facts and design decisions;
3. plan grill: dependency graph, risks and parallelism challenged;
4. implementation: bounded tasks with fresh contexts;
5. integration: contracts and cross-task behavior verified;
6. review/grill: requirements, architecture, security and edge cases;
7. smoke/evidence: build, startup, critical path and fresh command output;
8. closeout: state, deferred work, risks and continuation prompt.

## Prompt refinement

Run prompt refinement twice:

- **Input refinement:** convert a vague goal into context, scope, non-goals, constraints, acceptance criteria, validation commands and candidate waves.
- **Output refinement:** feed the plan, grill findings, decisions and residual risks into a prompt that can start the next session without relying on chat history.

The final prompt should be an artifact, not only a chat response.

## Anti-patterns

- many agents with overlapping ownership;
- parallel work before contracts and dependencies exist;
- a monitor that edits code or hides failures;
- treating a checkpoint as completion of a standing goal;
- trusting worker reports without independent verification;
- implementing the orchestrator runtime before schemas, state transitions and validation are deterministic;
- adding provider-specific dispatch logic to the PD core too early;
- marking a task complete because a subagent claims files/tests exist without reading the files and rerunning the exact commands;
- accepting a green focused slice while an independent review still has a blocker/high finding;
- allowing a supplied adapter to replace a built-in safe adapter, or checking idempotency before security validation;
- exposing mutable cached results, registries, reports, or adapter errors to callers;
- treating JSON as safe without rejecting NaN/Infinity, invalid IDs, inconsistent identity fields, or malformed lifecycle metadata.

## Adversarial hardening learned from fleet implementation

For dispatchers, adapters, checkpoints, and orchestrators, add security/state-machine probes before approval:

1. **Default-deny integrity:** built-in safe adapters must be private or immutable; test both constructor-time and post-init replacement attempts. Unknown/external adapters must fail closed without echoing untrusted names, secrets, or exception text.
2. **Validation ordering:** validate task/context shape, credentials, URLs, and sensitive fields before idempotency/cache lookup. A denied second request must not become accepted because the task ID was previously cached.
3. **Recursive input inspection:** scan mappings, sequences, dataclasses, object attributes and safe `to_dict()` results; inspect sensitive field names as well as values; detect embedded URLs, cycles, excessive depth, and property/introspection failures without uncaught recursion/runtime errors.
4. **Defensive boundaries:** return deep copies from cache, history, reports, and result payloads. Do not expose mutable adapter registries or internal records through public attributes.
5. **Strict persistence:** checkpoint/state validators must reject non-string or inconsistent IDs, invalid attempt/max-attempt values, bad retryability/status fields, unsupported schema versions, and NaN/Infinity. Atomic writes need rollback tests for replacement failure, absent primaries, stale backups, and rollback failure.
6. **Review loop:** after every fix cycle, rerun the full suite and dispatch fresh reviewers that did not implement the fix. A focused test count is evidence for the slice, never evidence that the whole gate passed.

Keep these probes in the umbrella workflow; details for a session belong in a `references/` file or regression test, not in the chat-only report.

## First implementation sequence

1. schemas, templates and deterministic DAG/path validation;
2. fleet/task status and eligible-task inspection;
3. checkpoint/resume and explicit failure states;
4. provider-agnostic dispatch/report adapter;
5. review, grill, smoke and evidence gates;
6. input/output prompt refinement;
7. self-hosted example proving the PD workflow end to end.
