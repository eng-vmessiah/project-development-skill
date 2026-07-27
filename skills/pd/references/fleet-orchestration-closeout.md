# Fleet orchestration closeout hardening

Use this reference after implementing a local/simulated fleet or multi-agent orchestrator. It captures the failure pattern found in a real implementation: the unit suite was green while the executable CLI and several runtime contracts were incomplete.

## Mandatory sequence after the first green wave

1. Run an independent spec-compliance review against every requirement, not just tests.
2. Run an independent quality/security review.
3. Run an adversarial grill against the real CLI/entrypoint and state boundaries.
4. Turn every confirmed blocker/high finding into an explicit remediation task; do not patch ad hoc or declare the plan complete.
5. Re-run fresh focused and full verification after remediation.
6. Write `VERIFICATION.md` with PASS/PARTIAL/BLOCKED per requirement and explicit caveats.

## Runtime probes that caught the important gaps

- Invoke the real CLI (`python scripts/pd.py fleet-run ...`), not only the Python API or example runner.
- Exercise normal, `--dry-run`, `--resume`, missing plan, malformed plan, partial-gate plan, and a plan with a transient failure.
- Assert return codes, JSON schema, state bytes/mtime, checkpoint loadability, and that completed tasks are not replayed.
- Run from a temporary working directory because this CLI resolves `.spec/` relative to the current directory; do not invent an unsupported `--root` flag.
- Verify `fleet-status` and `fleet-ready` after a run and confirm they do not rewrite state.

## Contracts that must be enforced at runtime

- A passed gate must be a complete, policy-validated `GateResult` with owner, decision, evidence, reports, and no blockers. Never authorize from `status: passed` alone.
- Retry must honor max attempts and retryable error classes/tokens; avoid substring matching that retries `not transient` for `transient`.
- `ready_tasks()` and execution must share the same inputs/`blocked_when` semantics.
- Completion must validate declared outputs, meaningful evidence, acceptance metadata, and agent role/capability compatibility.
- Sanitize successful output/evidence as well as errors before reports, hooks, checkpoints, or persistence.
- Every orchestrator-generated checkpoint must round-trip through the canonical checkpoint loader, including schema/version/feature/wave/timestamp metadata.
- The CLI must persist a complete fleet namespace atomically and must leave state untouched during dry-run.

## Evidence language

Distinguish these claims:

- **Local implementation verified:** tests and offline simulated execution passed.
- **PARTIAL:** requirements depending on command execution, external providers, human approval, or deployment identity remain unverified.
- **PASS:** only after fresh evidence covers the full stated scope and the required human gate is recorded.

Semantic determinism may be verified while raw output still varies in timestamps or absolute paths; document the normalization rule instead of claiming byte-identical output.

## Common false completion signals

- The subagent reports files/tests that were not independently checked.
- A focused suite passes but the CLI subcommand is missing or not wired into `main()`.
- An example runner works while the production entrypoint lacks dry-run/resume.
- A snapshot is emitted by a hook but cannot be loaded by the canonical checkpoint parser.
- A gate model is strict in isolation but the orchestrator uses a status-only fallback.
- A `VERIFICATION.md` says PASS while the grill still has open blockers.
