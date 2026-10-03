# Project Development Skills

A comprehensive skill ecosystem for AI-assisted software development. Works with **Hermes Agent**, **OpenCode**, and **Claude Code**.

## Versioned source releases

The authoritative package version is stored in [`VERSION`](VERSION). A `v*` tag
must exactly match that value; the release workflow reruns the repository checks
and publishes a reproducible `project-development-skill-<version>.tar.gz` source
archive with its `.sha256` checksum as GitHub release assets.

## What's Included

The repository currently contains **27 skills** (`SKILL.md` files), including the nested `engineering/` category:

| Skill | Category | Included skills |
|---|---|---|
| `pd` | Core | master orchestrator |
| `engineering/*` | Engineering | `codebase-design`, `resolving-merge-conflicts` |
| code quality | Code quality and architecture | `clean-code`, `ddd-development`, `design-patterns`, `service-composition` |
| security | Security and data | `auth-patterns`, `security-checklist`, `database-patterns` |
| AI/testing | AI and testing | `ai-optimization`, `ai-regression-testing`, `test-driven-development` |
| workflow | Workflow | `plan`, `spike`, `writing-plans`, `requesting-code-review`, `subagent-driven-development`, `systematic-debugging` |
| writing | Writing | `humanizer`, `writing-clearly-and-concisely` |
| delivery | Product and delivery | `api-design`, `documentation-patterns`, `deployment-patterns`, `monitoring-observability`, `performance-patterns`, `recipes` |

## Quick Install

```bash
git clone https://github.com/eng-vmessiah/project-development-skill.git
cd project-development-skill
chmod +x install.sh
./install.sh
```

The installer installs only into platform roots that already exist: Hermes at
`~/.hermes`, OpenCode at `~/.config/opencode`, and Claude Code at `~/.claude`.
It exits `2` if no supported root exists. A Hermes root also receives the `pd`
CLI runtime in `~/.hermes/bin/`; upgrades remove only paths recorded in the
installer manifest, not unrelated files. See [`docs/INSTALLER.md`](docs/INSTALLER.md).

## Manual Installation

Use the repository installer so nested skills, platform transformations, stale-file cleanup, and Claude flat-name collisions are handled consistently:

```bash
chmod +x install.sh
./install.sh
```

For a custom platform, reproduce the contracts in `skills/pd/references/multi-platform-skill-development.md`; do not copy `skills/*.md` because each skill lives in its own directory and may contain references/templates.

## Hermes Fleet adapter status

`HermesExistingReadOnlyAdapter` (in `scripts/pd_fleet/hermes_existing_adapter.py`)
wraps only an explicitly injected, existing Hermes read-only client. It can delegate
explicit session snapshot/replay/heartbeat surfaces when that client declares them,
and validates returned data through the Fleet bridge contracts. It does **not** add
network discovery, subprocess execution, credentials, state databases, control
methods, Fleet observer activation, global subscriptions, opaque activation tickets,
or issuer verification. The Fleet-owned seam and production capability therefore
remain explicitly `NOT_READY` (`NOT_READY_HERMES_SEAM`). The separate fake adapter
is test-only and is not a fallback for this adapter.

## Usage

### Hermes / OpenCode
```
skill_view(name='pd')
```

### Claude Code
```
/pd
```

The `scripts/pd` CLI is not read-only: `pd init <feature>` creates a feature
`.spec/` scaffold, and commands such as `checkpoint`, `advance`,
`complete-task`, and `verify` update project state. Fleet inspection commands
(`fleet-status`, `fleet-ready`, and `v2 read/status`) are read-only; the local
Fleet V2 runner is explicitly opt-in and simulated/default-deny.

## The PD Pipeline

```
Phase 0: Setup (worktree) → Phase 1: Brainstorming → Phase 2: Planning (.spec/)
→ Phase 3: Structure (.templates/) → Phase 4: Coding (wave-based)
→ Phase 5: Testing (TDD + bug-driven) → Phase 6: Validation (evidence-based)
→ Phase 7: Merge & Deploy
```

## Philosophy

- **No code without spec + plan** — The Prime Directive
- **Evidence-based completion** — No claims without fresh verification
- **Wave-based execution** — Fresh context for heavy work
- **Bug-driven coverage** — Test where bugs were found

## Templates

The `pd` skill includes templates for `TASK.md`, `CHECKPOINT.md`, and `STATUS.md`.
These are installed to Hermes `~/.hermes/skills/software-development/pd/templates/`
and OpenCode `~/.config/opencode/skills/pd/templates/`.

## Fleet Orchestration Evolution

The design and migration material is documented in:

- [`docs/PD-AS-IS-TO-BE.md`](docs/PD-AS-IS-TO-BE.md)
- [`docs/PD-FLEET-ORCHESTRATION-PLAN.md`](docs/PD-FLEET-ORCHESTRATION-PLAN.md)
- [`docs/PD-FIRST-CASE-PROMPT.md`](docs/PD-FIRST-CASE-PROMPT.md)

The offline fleet example (`examples/pd-fleet/run_local.py`) validates a local
plan before creating output files. Gate references are deterministic identities
resolved against validated records; unresolved references fail closed. Output
paths are contained beneath `--output`, symlink roots are rejected, and task IDs
must be safe path segments.

### Fleet V2: local-first, runtime-agnostic, and fail-closed

Fleet V2 is currently **merged as a local/experimental capability**. It is not
an operational production release, has no provider or live-network readiness
claim, and has no human G1–G6 approval recorded here.
The safe default is local simulation with an explicit plan and output directory;
no shell, network, external provider, credentials, or undeclared validation
command is invoked. The executable V2 local path is:

```bash
python3 scripts/pd.py v2 run-local --plan ./fleet-plan.json \
  --store ./.pd-fleet-runs --run-id demo --owner local --provider local
```

It uses the internal deterministic `simulated` adapter, persists a bounded report,
validation/evidence and lifecycle state, and returns the persisted completed run
on idempotent re-invocation. A persisted run can be inspected read-only:

```bash
python3 scripts/pd.py --json v2 inspect \
  --store ./.pd-fleet-runs --run-id demo
```

A readiness gate read-only is available for automation:

```bash
python3 scripts/pd.py --json v2 readiness \
  --store ./.pd-fleet-runs --run-id demo
```

It returns `ready=true` only when the persisted run and every report are completed; incomplete, failed, blocked, cancelled or unknown states return `ready=false` with a bounded reason. External execution is deferred and, if proposed later,
requires exact argv allowlisting, containment/sandbox, timeout, redacted bounded
output, and a separate explicit release decision.

The architecture is runtime-agnostic:

- `pd-only`: PD Core without Fleet or Hermes;
- `fleet-local`: local/simulated Fleet without Hermes, credentials, network, or providers;
- `fleet-hermes`: optional Hermes adapter/plugin (`pd-fleet-hermes`) selected by capabilities and separate gates.

The Hermes plugin is a thin integration layer for tools, commands, lifecycle hooks,
and session translation. The Fleet scheduler, persistence, checkpoints, DAG, gates,
and reports remain outside the plugin.

See [`docs/PD-FLEET-RUNTIME-ADAPTERS.md`](docs/PD-FLEET-RUNTIME-ADAPTERS.md). Hermes
integration is not required to use the PD skill or local Fleet.

Migration preserves V1 state and uses a separate V2 namespace/output; rollback
stops dispatch, invalidates leases, and restores the last valid snapshot without
rewriting V1. The implemented offline checker
`scripts/pd_fleet/v2_doc_paths.py` validates V2 path/link declarations and fails
closed on root/document symlinks. A valid checker result does not authorize
provider dispatch or production release. See the [current verification and
provenance index](docs/PD-FLEET-V2-VERIFICATION.md).

## License

MIT

## Credits

Inspired by Clean Code, Domain-Driven Design, Design Patterns (GoF), GEPA,
iii service composition primitives, and evidence-based validation patterns.
