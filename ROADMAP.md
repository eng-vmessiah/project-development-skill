# Roadmap

This document outlines the development roadmap for Project Development Skills.

## Current state (feature branch)

The tree currently contains 27 skills, a multi-platform installer, the `pd` CLI,
and local/experimental Fleet V2 capabilities. No new published version is
claimed by this document; release metadata remains a separate decision.

| Category | Skills | Status |
|---|---|---|
| Core | `pd` | Implemented |
| Engineering | `engineering/codebase-design`, `engineering/resolving-merge-conflicts` | Implemented |
| Code quality and architecture | `clean-code`, `ddd-development`, `design-patterns`, `service-composition` | Implemented |
| Security and data | `auth-patterns`, `security-checklist`, `database-patterns` | Implemented |
| AI and testing | `ai-optimization`, `ai-regression-testing`, `test-driven-development` | Implemented |
| Workflow | `plan`, `spike`, `writing-plans`, `requesting-code-review`, `subagent-driven-development`, `systematic-debugging` | Implemented |
| Writing | `humanizer`, `writing-clearly-and-concisely` | Implemented |
| Product and delivery | `api-design`, `documentation-patterns`, `deployment-patterns`, `monitoring-observability`, `performance-patterns`, `recipes` | Implemented |

**Implemented infrastructure:**
- Installer for Hermes Agent, OpenCode, and Claude Code with existing-root detection,
  owned manifests, nested-skill copying, stale-owned-file cleanup, and Claude
  flat-name collision handling.
- CLI commands for initialization, status, validation, checkpoint/state mutation,
  verification, task completion, history/reporting, and diff; fleet inspection
  commands are read-only by design.
- Templates, recursive skill validation, documentation path checking, and tests.

## Phase 1: Foundation — completed

- [x] Master `pd` skill with the eight-phase pipeline
- [x] 27 skills, including nested engineering skills
- [x] Multi-platform installer and CLI runtime packaging
- [x] CLI state creation and mutation commands
- [x] Templates and repository test suite
- [x] Documentation and REST API example

### Still open in the foundation

- [ ] Comprehensive example coverage (web app, CLI tool)
- [ ] CI artifact collection for test results
- [ ] More cross-skill recommendations and composition guidance

## Phase 2: Expansion — deferred

Specialized skills already present in the tree are not future work. Remaining
roadmap work includes cross-skill recommendations, custom template support,
CLI performance benchmarks, plugin hooks, and additional examples. Potential
future domains include monitoring improvements, deployment recipes, and other
community-requested skills; no release versions are assigned here.

## Phase 3: Ecosystem — future

- IDE integrations (VS Code, JetBrains, Vim/Neovim)
- Community skill registry and contribution workflow
- Versioned skill dependencies and runtime interaction validation
- Project-management integrations and skill recommendation features

## PD Core, PD Fleet, and Runtime Adapters

The current boundary is intentionally local and non-production:

- **PD Core** owns the development workflow, SPEC/PLAN, gates, evidence
  interpretation, and human delivery decisions. It runs in `pd-only` mode without
  Fleet, Hermes, providers, or credentials.
- **PD Fleet** is an optional local/simulated coordination extension for task
  lifecycle, dependencies, leases, reports, checkpoints, events, and reconciliation.
  Its reference mode is `fleet-local`, which must work without Hermes installed.
- **Runtime adapters** are optional capability-based integrations selected explicitly
  (`none`, `local`, `hermes`, or future OpenCode/Claude/other adapters). The Fleet
  scheduler must block unsupported capabilities rather than assume a runtime.
- **Hermes Runtime/Gateway** owns sessions, `delegate_task`, providers, models,
  tools, credentials, cron, effective runtime capabilities/policy, and the
  JSON-RPC/WebSocket/event surfaces used by Hermes clients. Hermes is an adapter,
  not a prerequisite for PD or local Fleet.
- **Hermes Gateway Fleet Bridge** is an optional future adapter/plugin track, conceptually
  `pd-fleet-hermes`. B15a first evaluates the plugin against the local TUI backend for
  one active session; B15b separately evaluates the plugin against the messaging/API
  Gateway. The plugin is opt-in and does not contain the Fleet Core. No real bridge,
  provider activation, or live dispatch is activated by this roadmap.
- **OMH** is reference material for workflow patterns and learning only. It is not
  installed, integrated, scheduled, synchronized, or authoritative.

Fleet V2 remains **PARTIAL/OPEN**, local/experimental, and default-deny. Its
simulated runner, contracts, checkpoints, gates, inspection commands, and offline
documentation checker are local capabilities only. They do not constitute provider
execution, live-network dispatch, production deployment, a strong production
sandbox, or human G1–G6 approval. See
[`docs/PD-FLEET-V2-VERIFICATION.md`](docs/PD-FLEET-V2-VERIFICATION.md) for current
verification and provenance pointers.

### Deferred runtime and operational work

The following require separate scope, design, security evidence, and explicit
approval; they are not prerequisites for PD Core or the local Fleet mode:

- [x] Local fake Fleet/runtime adapter seam and controlled fake-delegate verification
- [x] Runtime adapter capability contract and Hermes-independent local adapter verification
- [ ] Hermes TUI → Fleet adapter plugin (`pd-fleet-hermes`, B15a)
- [ ] Hermes messaging/API Gateway → Fleet adapter plugin (`pd-fleet-hermes`, B15b)
- [ ] Real Fleet-owned task adapter, provider activation, and live dispatch
- [ ] Provider/runtime activation, live dispatch, credentials, and external execution
- [ ] Strong sandboxing, deployment, shared persistence, multi-host workers, and HA
- [ ] Operational observability, canary/rollback, runbooks, and G1–G6 evidence
- [ ] OMH adapter, runtime/state synchronization, or scheduling integration

## Known limitations

1. Fleet V2 is local simulation only; provider/live/production claims are out of scope.
2. Fleet scheduling, leases, parallelism, ownership, and resume contracts require
   further end-to-end evidence before live use.
3. CLI state mutation exists, but custom template fields and incremental resume
   semantics remain limited.
4. Skills do not automatically generate cross-references in their output.
5. Some skills are large and could benefit from further modularization.
6. Examples remain limited in domain diversity.

## How to contribute

See [`docs/CREATING-SKILLS.md`](docs/CREATING-SKILLS.md), add tests for executable
components, update the changelog, and run the repository checks before submitting.

## Versioning strategy

The project follows [Semantic Versioning](https://semver.org/). A release is not
implied by this roadmap. The authoritative version is [`VERSION`](VERSION):
update `CHANGELOG.md`, commit it, tag the exact `v<version>`, and run the release
workflow only as part of an explicit release decision. The workflow publishes a
reproducible source archive and SHA-256 checksum for that tag.

*This roadmap is a living document. Priorities may shift based on community feedback.*
