# Generic Platform PDS

Use this reference when a project has a concrete MVP but the intended product is a reusable automation platform.

## Project identity first

When multiple related initiatives exist, identify the exact project and canonical plan before summarizing status. Read the target README, canonical plan, checkpoint, and repository state. Do not substitute a neighboring project with overlapping vocabulary. If the user corrects the project, acknowledge the mismatch, recover the correct source of truth, then continue.

## Architecture pattern

Separate:

- **Platform Core:** versioned contracts, tenancy, lifecycle, policies, evidence, QualityCheck, audit and usage;
- **Employee Agent Runtime:** Profile + Workflow + TenantContext + tools/budget/policies;
- **Domain Pack:** domain schemas, adapters, deterministic rules, exceptions and reports.

Use a synthetic read-only Fake Domain Pack as the first executable slice. It validates the Core without inventing client rules or contaminating generic contracts with domain fields. Defer a public SDK/framework until a second Domain Pack validates the abstractions.

Recommended sequence:

```text
G0 preflight/grill → G1 contracts → G2 local runtime
→ G3 fake vertical slice → G4 operator surface
→ A0/A1 external-runtime spike → real Domain Pack after discovery
```

Keep external runtimes and effects default-deny. Local/fake verification is not live readiness.

## PD validator bootstrap

Before implementation, create `.spec/<feature>/README.md`, `SPEC.md`, `PLAN.md`, `CONTEXT.md`, `RESEARCH.md`, `STATE.md`, `STATE.json`, `CHECKPOINT.md`, `VERIFICATION.md`, `DECISIONS.md`, and a non-empty test scaffold if required by the validator.

For `pd validate --deep`:

- `SPEC.md` needs checkbox requirements;
- `PLAN.md` needs checkbox tasks;
- `CONTEXT.md` needs `## Decisions` with bullet decisions;
- `STATE.json` must use CLI-native types, notably integer `phase` and `tasks` as a list of completed task strings or an empty list.

Run deep validation before authorizing the first coding wave. Fix structure/schema failures instead of bypassing validation.
