# Documentation-only reconciliation after an independent review

Use this procedure when a wave is blocked by an external seam, missing owner approval, or unresolved security contract. Do not convert review findings into implementation work.

1. Preserve the blocked/readiness state explicitly in plan and state artifacts (for example, `blocked_pending_plan_approval` plus the live `NOT_READY_*` status).
2. Convert convergent review findings into named contract blockers, not vague TODOs: seam/API ownership, trusted identity binding, composite default-deny precedence, closed schemas and bounds, redaction-before-buffering, replay/cursor/TTL/restart semantics, and lifecycle authority.
3. Reconcile vocabulary when adjacent layers use different operation names. State which names are control-plane versus transport-plane, and require one authoritative wire vocabulary before implementation; never silently alias proposed APIs.
4. Add a minimum evidence packet that separates contract-only, fake/injected, process-level, real seam, and live-authorized evidence. Local verification must not promote live readiness.
5. Re-run documentation/path checkers and `git diff --check`, inspect the complete diff, and leave WIP uncommitted unless commit authorization was explicit.

Completion requires plan, master plan, state, and normative contracts to agree on the blocker, with no code/runtime checkout touched. If the umbrella SKILL.md cannot be patched because it exceeds the library size limit, keep this reference discoverable through the skill's linked files and report the maintenance limitation rather than inflating the skill further.
