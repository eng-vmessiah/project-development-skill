# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Installer coverage for existing platform roots, owned manifests, nested skills,
  stale-owned-file cleanup, and the packaged Hermes `pd` CLI runtime.
- CLI workflows for feature initialization and project-state mutation alongside
  validation, status, checkpoint, verification, task completion, history,
  reporting, and diff inspection.
- Recursive skill validation and the offline Fleet V2 documentation path checker.
- Current Fleet V2 verification/provenance index and reconciled skill documentation.

### Changed
- Documentation now inventories the 27 skills, including nested engineering
  categories, and documents the repository's actual GitHub URL.
- Lint and documentation checks are described as local/offline verification; no
  provider, live-network, or production-readiness claim is made.

### Fleet V2: local/experimental
- Local simulated plan validation, deterministic dispatch/output, contracts,
  gates, checkpoints, inspection, and default-deny boundaries are documented as
  current capabilities.
- Known limitations remain: no delivered provider/live execution, no production
  approval, no human G1–G6 approval, and incomplete evidence for parallelism,
  ownership, leases, resume, and operational rollback.

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
