# PD/Fleet Scope Alignment

This is the active scope-reset and hardening plan for the next local Fleet wave.

## Read order

1. `SPEC.md` — goal, boundaries, non-goals, success criteria.
2. `CONTEXT.md` — baseline, decisions, parallelism and safety policy.
3. `PLAN.md` — waves, task contracts, dependencies and verification.
4. `STATE.md` — current execution state.
5. `VERIFICATION.md` — created only after fresh verification.

## Product boundary

```text
PD = development workflow and decisions
Fleet = optional local coordination/state engine
Hermes = runtime host, delegate_task and cron
OMH = learning/reference only
```

This plan does not authorize live providers, network, credentials, subprocesses, production sandboxing, deployment, merge, push, release, or service restart.
