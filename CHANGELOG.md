# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `pd init --template-dir` accepts custom `SPEC.md`, `PLAN.md`, and/or `CONTEXT.md`
  templates with a `{{feature}}` placeholder and per-file fallback; invalid or
  symlinked templates fail before the feature directory is created.
- `scripts/bench_cli.py` measures `pd init/status/complete-task/list` latency on
  disposable fixtures; `docs/BENCHMARKS.md` records the baseline and caveats.
  Advisory only, no CI threshold.
- `scripts/release_preflight.sh` runs the CI/release gates locally: pytest,
  flake8, skill validation, validator/installer regressions, release archive,
  Markdown links, V2 documentation paths, and shell syntax. `--release` also
  checks a clean tree and that the tag points at `HEAD`.
- `scripts/check_markdown_links.py` is the single Markdown-link checker used by
  both GitHub workflows and the preflight.

## [1.3.3] - 2026-11-08

Third fix-forward release for `v1.3.0`. `v1.3.2`'s tests passed, but the release
workflow's Markdown link check rejected a literal Markdown link example inside
an inline code span in `.spec/reviews/docs-20261102.md`. The `v1.3.2` tag is
preserved; the review note now names the target without embedding a link.

### Fixed
- The docs review note no longer embeds a relative Markdown link inside an inline
  code span, so the tracked-link check passes.

## [1.3.2] - 2026-11-08

Second fix-forward release for `v1.3.0`. `v1.3.1`'s release workflow stopped at the
same pilot-runner test because the sandbox test trusted `/bin/echo`, which the
runner rejects on that image. Both tags are preserved unmodified; the fix is
forwarded here.

### Fixed
- Pilot-runner tests use the resolved Python interpreter as the trusted binary and
  execute a harmless `-c` probe, so the suite no longer depends on a
  distro-specific `/bin/echo` layout.

## [1.3.1] - 2026-11-08

Fix-forward release for `v1.3.0`, whose release workflow stopped before publishing:
the pilot-runner tests assumed the maintainer's `/home/vitor` home. This tag's
workflow also stopped on CI (the sandbox test still trusted `/bin/echo`); the tag
is preserved and the fix is forwarded in 1.3.2.

### Fixed
- The pilot runner resolves the Hermes executable from `PD_HERMES_EXECUTABLE` or
  `~/.local/bin/hermes` instead of a hardcoded home, and builds its child
  `PATH`/`HOME` from the environment.
- Pilot-runner tests use a portable trusted binary, so the release suite passes
  on CI runners without a Hermes install.

## [1.3.0] - 2026-11-08

Release workflow stopped before publishing because the pilot-runner tests
hardcoded the maintainer home; the tag is preserved and the fix is forwarded
through 1.3.1 to 1.3.2.

### Added
- **Fleet V2 local vertical slice**: bounded run inspection, readiness gates,
  capability-gated dispatch adapters, bounded parallel execution, and
  deterministic retry/recovery fixtures.
- **B15b gateway (local/fixture)**: local auth and association, composite-deny
  and redaction validators, subscription v1 (ordering/ack/TTL/explicit gaps),
  a replayable observer seam, rollback rehearsal, and live-validation evidence.
  The live seam is currently `NOT_READY_HERMES_SEAM` after a Hermes host update;
  nothing activates automatically.
- **Plan cockpit**: derived-only `plan_cockpit_sync.py`, Mission Control tab,
  stable file bindings, 30-minute refresh cron, mission selector, and a gated
  pilot runner (3/3 real runs).
- **Fleet control plane**: activity contract v1, read-only swarm surface,
  steering contract (design-only), `plan.yaml` validation, and the 12th/13th
  `pd validate --deep` checks.
- **PD CLI**: human-gate flags for `fleet-run` (`--run-id`, `--human-gate`,
  `--gate-template`), plan.yaml manifest validation, legacy `done` →
  `completed` migration, and synchronized bash/zsh/fish completions.
- **Board connector**: stdio MCP `pd` connector with action buttons for the
  pds/fleet/mc syncs and reproducible v2 payloads.
- **Laya routing advisory spike**: measured sink 14% / notify 71% vs baseline,
  no wire; decisions recorded for future calibration.
- Contract guard tests for `plan-cockpit-v1` and `b15b-gateway`;
  `pd validate --deep` reaches 13/13 on both.

### Changed
- Lint target pinned to Python 3.10; the Ruff hygiene pass reduced 271 findings
  to 0, with documented `noqa` only at containment/best-effort boundaries.
- Dashboard payloads moved to live file bindings; mission/feature snapshots are
  derived from real `.spec` sources only.
- The `pd` interpreter is pinned in `~/.venvs/pd` (PyYAML/jsonschema).

### Fixed
- **D1**: cross-process `STATE.json` updates now take a lock, re-read the file,
  and 3-way merge instead of losing updates.
- Closed 5 of 6 code-review defects with a regression test per defect; the
  remaining item is tracked in the review record.
- `FleetRunStore` read-only paths share the writer constructor
  (`readonly=True`), avoiding missing attributes and lock creation.
- Shell completions now derive from the argparse surface and stay in sync.
- Cockpit collector counts `completed` as terminal, fixing task drift.
- Renamed a pytest `setup` helper that collided with nose compatibility and
  silently errored 30 bridge tests.
- Malformed `STATE.json` records are skipped instead of aborting the run.

### Security
- Composite-deny and redaction validators for the gateway surface; fail-closed
  auth/association and bounded payload validation.

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
| 1.3.3 | 2026-11-08 | Fix-forward: review note no longer embeds a Markdown link in a code span (v1.3.2 link check failed) |
| 1.3.2 | 2026-11-08 | Fix-forward: sandbox test uses the resolved interpreter (release workflow failed at Markdown link check; carried forward in 1.3.3) |
| 1.3.1 | 2026-11-08 | Fix-forward: portable pilot-runner executable/env (release workflow failed; carried forward in 1.3.2) |
| 1.3.0 | 2026-11-08 | Fleet V2/control plane/plan cockpit, B15b local, CLI human gates, board connector, Ruff 271→0 (release workflow failed; carried forward through 1.3.1/1.3.2 to 1.3.3) |
| 1.2.1 | 2026-10-03 | Patch: release workflow test-dependency fix (carries 1.2.0 forward) |
| 1.2.0 | 2026-10-03 | Skill-source reconciliation, B15a local closeout, CI repair |
| 1.1.1 | 2026-07-28 | Directory/executable pin validation fix |
| 1.1.0 | 2026-07-28 | Installer coverage, CLI workflows, release CI, Fleet V2 docs |
| 1.0.0 | 2026-06-14 | Initial release with 17 skills |
