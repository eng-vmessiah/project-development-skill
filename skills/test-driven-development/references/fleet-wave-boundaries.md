# Fleet scheduler and capability-gate regression patterns

Use this reference when adding local Fleet concurrency or adapter-boundary behavior.

## Red-first cases that are easy to miss

1. **Wave barrier must use all non-terminal tasks, not only currently-ready tasks.**
   A task from wave 1 that is leased/running is not ready, but it must still prevent a dependency-free task from wave 2 from being claimed. Reproduce with `max_parallel=2`: claim wave-1 task, then assert both `ready_ids()` and a second claim do not release wave 2.

2. **Validate scheduling metadata across the complete plan before selection.**
   Invalid `wave` values must fail even if the malformed task is terminal, leased, or dependency-blocked. Do not only validate candidates produced after readiness filtering.

3. **Effective capability means an intersection, not a profile or adapter claim alone.**
   At a dispatch boundary, calculate:
   `adapter.capabilities ∩ selected profile capabilities ∩ policy allowed capabilities`.
   Requests outside that intersection must return a stable blocked/audited result before runner lookup, envelope construction, or adapter execution.

4. **Legacy structural adapters must fail closed without side effects.**
   If an adapter lacks a new capability-declaration method, return an explicit blocked result and assert zero execution calls. Do not silently infer capabilities from its profile.

## Review checklist

- Start with an intentionally failing test and capture the observed failure.
- Add a second-claim regression for lease/race-sensitive scheduler behavior.
- After focused GREEN, run the Fleet suite, `compileall`, and `git diff --check`.
- Use an independent reviewer before committing a wave. Treat reviewer findings as blockers; add a regression test for each accepted finding before changing production code.
- Keep capability, scheduler, and CLI changes in separate commits when their files and acceptance gates can be isolated.
