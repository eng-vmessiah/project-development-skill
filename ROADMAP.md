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

## Fleet orchestration — local V2 now, live work deferred

Fleet V2 is **PARTIAL/OPEN**, local/experimental, and default-deny. The local
simulated runner, contracts, checkpoints, gates, inspection commands, and offline
documentation checker are implemented capabilities. They do not constitute a
provider adapter, live-network execution, production readiness, or human G1–G6
approval. See [`docs/PD-FLEET-V2-VERIFICATION.md`](docs/PD-FLEET-V2-VERIFICATION.md)
for current verification and provenance pointers.

Genuinely deferred Fleet/live work:

- [ ] Provider-agnostic live dispatcher and runtime adapters
- [ ] External execution with explicit allowlists, sandbox, timeout, redaction,
      credentials policy, and release approval
- [ ] Demonstrated safe parallel execution and ownership/conflict isolation
- [ ] Operational G1–G6 evidence and human approval
- [ ] Prompt refinement, production observability, and operational rollback

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
implied by this roadmap: update `CHANGELOG.md`, choose a version, tag it, and run
the release workflow only as part of an explicit release decision.

*This roadmap is a living document. Priorities may shift based on community feedback.*
