# PD/Fleet Scope Alignment — Context

## Immutable baseline

- Repository: `/home/vitor/project/project-development-skill`
- Branch observed: `release/pd-v2-hardening`
- HEAD observed: `c14b333 chore: prepare 1.1.1 patch release`
- Working tree: clean at planning start
- Existing status: H01–H03 resolved locally; H04–H06 open; GRILL-001 remains blocked/not ready.

## Architectural decisions

1. **PD is the product workflow.** It owns goal interpretation, SPEC, PLAN, acceptance, development gates, evidence interpretation, and delivery decisions.
2. **Fleet is optional execution coordination.** It owns task lifecycle, dependencies, leases, reports, checkpoints, events, and local simulation.
3. **Hermes is the runtime host.** It owns `delegate_task`, cron, sessions, tools, providers, credentials, models, and effective capability/sandbox policy.
4. **OMH is learning/reference only.** No runtime or state integration is approved.
5. **Local Fleet correctness is the current target.** Production runtime readiness is deferred and must not block this plan.
6. **PD .spec state describes development intent and decision; Fleet run state describes execution; Hermes session state describes concrete runtime execution.** These are related but not interchangeable.

## Parallelism policy

- Parallelize documentation tasks only when each worker owns distinct files.
- Parallelize H04 and H06 after the scope/reclassification gate because their primary code/test ownership is distinct.
- H05 depends on the H04 lease/claim contract and is sequential after H04.
- Never run two writers against the same file/worktree.
- Reviews are fresh, read-only, and occur after implementation evidence exists.
- A reviewer cannot approve its own implementation.

## Safety and delivery policy

- Provider, network, live dispatch, subprocess execution, and production sandbox remain disabled.
- Subagents must not broaden file scope or create unplanned integrations.
- Subagent summaries are hypotheses; the parent verifies files, diffs, tests, and artifacts.
- No commit, push, merge, release, deploy, or restart is implied by this plan.

## Historical material

The existing V2 plan and GRILL-001 remain historical evidence and findings. This plan supersedes their assumption that local Fleet hardening is a prerequisite for production readiness. It does not erase their findings or alter V1 behavior.
