# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.2.1] - 2026-10-03

Patch release carrying the 1.2.0 content forward. The `v1.2.0` tag's release
workflow failed before publishing because the release workflow's test-dependency
install did not include `jsonschema` (required by the Fleet schema-validation
tests and fixtures) — the same class of gap repaired in the main CI workflow for
1.2.0. Per the release policy, the failed tag is preserved unmodified and the fix
is forwarded here.

### Fixed
- The release workflow now installs the `jsonschema` test dependency, matching
  the main CI workflow.

## [1.2.0] - 2026-10-03

This release promotes the skill-source reconciliation and the Hermes gateway/fleet
adapter (B15a) local closeout to `main`, and repairs the CI pipeline. All Fleet and
Hermes-adapter work remains local/experimental; no live runtime activation is claimed
or included.

### Added
- **Hermes gateway/fleet adapter (B15a), local slice**: opt-in `pd-fleet-hermes`
  plugin package (lifecycle-only, default-off), versioned plugin and integration
  contracts, read-only TUI request/host-binding/capability/response contract, D1
  atomic batch registration port, local/injected composition canary, bounded binding
  lifecycle registry, and the runtime-readiness packet that gates any future
  installation or activation under its own authorization.
- **Fleet V2 local vertical slice**: bounded local run inspection, readiness gate,
  capability-gated dispatch adapters, bounded parallel local execution, deterministic
  retry/recovery fixtures, and bounded simulated output names.
- **Decision and review records**: B15a decision matrix D1–D7 with recorded approvals,
  the TUI wire contract, the delivery/recovery contract, the test matrix, the G8
  closeout verification, and the independent external-reference audit record.
- **Skill-source reconciliation**: restored 37 files that existed only in deployed
  skill installations, plus the reconciliation process reference.

### Changed
- Skill content is reconciled between this repository and deployed installations;
  internal-specific identifiers are generalized for the public repository.
- `pd` skill documentation and references now match the canonical slim form shipped
  by the installer.
- README and installer documentation updated for manifest-owned installs across
  Hermes, OpenCode, and Claude.

### Fixed
- CI collection failure on Python 3.11 (dataclass default rejected as unhashable),
  missing `jsonschema` dependency in the CI workflow, and unused-import lint failures
  (`F401`). CI is green across Python 3.10/3.11/3.12, lint, validate, and docs jobs.
- Bounded simulated report output names for deterministic runs.

### Fleet & Hermes adapter: local/experimental limitations
- The `pd-fleet-hermes` plugin and the read-only Fleet RPC remain **default-off** and
  `LIVE_NOT_READY`: no installation into an active runtime, no activation, no
  provider/network/credential use, and no task dispatch are included in this release.
- Installation, configuration, discovery, and activation each require a separate,
  scoped authorization recorded in the runtime-readiness packet.

### Planned
- Additional examples (web/CLI), CI artifacts, and cross-skill references.
- B15a.2 host integration under its recorded authorization; B15b (messaging/API
  gateway) remains a separate, not-started decision.

## [1.1.1] - 2026-07-28

This patch release fixes the directory/executable validation pin distinction
revealed by CI and was verified by the full 1048-test suite.

### Fixed
- Directory pins now track directory identity without mutable size/mtime
  metadata, while executable pins retain metadata so executable replacement is
  detected reliably.

## [1.1.0] - 2026-07-28

This additive release is identified by the authoritative [`VERSION`](VERSION)
file and is published from an exact `v1.1.0` Git tag by the release workflow.

### Added
- Installer coverage for existing platform roots, owned manifests, nested skills,
  stale-owned-file cleanup, and the packaged Hermes `pd` CLI runtime.
- CLI workflows for feature initialization and project-state mutation alongside
  validation, status, checkpoint, verification, task completion, history,
  reporting, and diff inspection.
- Recursive skill validation, shell regression coverage, and the offline Fleet V2
  documentation path checker.
- Release CI that reruns tests, validator, installer, link, documentation, and
  lint checks, then publishes a reproducible source archive and SHA-256 checksum.
- Current Fleet V2 verification/provenance index and reconciled skill documentation.

### Changed
- Documentation now inventories the 27 skills, including nested engineering
  categories, and documents the repository's actual GitHub URL.
- Lint and documentation checks are explicitly local/offline verification; this
  release makes no provider, live-network, or production-readiness claim.

### Fleet V2: local/experimental limitations
- Local simulated plan validation, deterministic dispatch/output, contracts,
  gates, checkpoints, inspection, and default-deny boundaries are documented as
  current capabilities.
- Fleet V2 remains local/experimental: there is no delivered provider/live
  execution, production approval, or human G1–G6 approval.
- Evidence remains incomplete for parallelism, ownership, leases, resume, and
  operational rollback; those capabilities are not approved by this release.

### Planned
- Additional examples, cross-skill recommendations, skill modularization, and
  genuinely deferred provider/live Fleet work.

## [1.0.0] - 2026-06-14

### Added
- Initial release with the original 17-skill ecosystem, multi-platform installer,
  templates, README, contribution guide, and MIT license.
- Core, pattern, quality, AI, writing, and utility skills as recorded at release.

---

## Version History

| Version | Date | Changes |
|---|---|---|
| 1.2.1 | 2026-10-03 | Patch: release workflow test-dependency fix (carries 1.2.0 forward) |
| 1.2.0 | 2026-10-03 | Skill-source reconciliation, B15a local closeout, CI repair |
| 1.1.1 | 2026-07-28 | Directory/executable pin validation fix |
| 1.1.0 | 2026-07-28 | Installer coverage, CLI workflows, release CI, Fleet V2 docs |
| 1.0.0 | 2026-06-14 | Initial release with 17 skills |
