# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

No changes yet.

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
| 1.0.0 | 2026-06-14 | Initial release with 17 skills |
