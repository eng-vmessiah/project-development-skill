# Skill-repository PDS review

Use this reference when the project being planned is itself a development-process or skill library repository.

## Minimum documentation-only package

Before implementation, create or reconcile a focused PDS containing:

- `README.md`: document map, scope, and guardrails;
- `SPEC.md`: problem, requirements, non-goals, success criteria;
- `CONTEXT.md`: repository structure, source/install boundaries, and authority rules;
- `RESEARCH.md`: current skill inventory, linked references, overlaps, and evidence;
- `PLAN.md`: waves, ownership, dependencies, review gates, rollback;
- `STATE.md`: current phase and exact resume point;
- `VERIFICATION.md`: fresh checks, limitations, and explicit status labels.

Use the repository's native layout when it already has one; do not create a competing plan tree merely to satisfy a generic template.

## Gate sequence

1. **Inventory:** inspect the target umbrella skill, linked files, adjacent class-level skills, and any naming collisions.
2. **Scope alignment:** state what belongs in the skill library versus the product/runtime repository. Keep runtime/provider/deployment work explicitly out of a documentation-only wave.
3. **Artifact review:** independently review the PDS for contradictions, stale statuses, missing gates, and accidental overclaiming.
4. **Wave release:** assign non-overlapping paths and explicit dependencies. Parallelize only independent writers.
5. **Two-stage review:** after implementation, run specification review and quality/security review separately. A timeout or missing verdict leaves review pending.
6. **Fresh verification:** rerun structural checks after final edits and re-read long plan/state sections to detect accidental deletion.

## Handoff status

Report these independently:

- `implemented`: files or code exist;
- `verified`: current commands/checks passed;
- `review pending`: independent review absent or unresolved;
- `deferred`: intentionally outside this wave;
- `blocked`: prerequisite or authorization missing.

A passed documentation gate means only that the next local wave may begin. It is not production, provider, sandbox, merge, release, or deployment approval.

## Common failure modes

- Treating a prior summary or worker report as proof without inspecting the current repository.
- Creating a narrow one-session skill instead of extending the existing umbrella.
- Claiming a whole plan is complete after a documentation checkpoint.
- Parallel writers sharing a file or an unclosed ownership boundary.
- Patching a long `PLAN.md` or `STATE.md` without re-reading neighboring gates.
- Using a force flag to conceal missing planning artifacts or stale state.
