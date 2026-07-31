# PD/Fleet Scope Alignment — Specification

## Status

**Draft approved for planning; implementation not started.**

## Problem

The repository evolved from a Project Development skill into a monorepo containing PD Core, a local Fleet coordination engine, runtime/provider adapters, and platform integration material. The implementation and verification plans currently mix local Fleet correctness with production-runtime expectations that belong to Hermes or a future operational project.

Without an explicit scope reset, hardening may continue toward the wrong product boundary, while PD, Fleet, Hermes, and OMH acquire overlapping authority.

## Goal

Define and implement a truthful local scope in which:

1. PD owns development workflow, plans, gates, evidence interpretation, and human decisions.
2. PD Fleet is an optional local/simulated coordination extension for tasks, dependencies, lifecycle, leases, reports, checkpoints, and reconciliation.
3. Hermes remains the runtime host and owns `delegate_task`, sessions, providers, models, cron, tools, credentials, and effective capabilities.
4. OMH is used only as a source of workflow patterns and learning; it is not installed, integrated, scheduled, or treated as a source of truth.
5. H04, H05, and H06 are resolved only to the extent required for a correct local Fleet protocol; no production readiness claim is made.

## Requirements

- [ ] Architecture documentation distinguishes PD Core, PD Fleet, runtime adapters, and Hermes.
- [ ] The plan explicitly excludes Fleet cron, production deployment, live providers, strong production sandboxing, multi-host execution, and operational OMH integration.
- [ ] GRILL-001 findings are reclassified as retained local correctness work, deferred runtime work, or superseded by scope.
- [ ] H04 has a regression proving dependency invalidation between readiness observation and lease claim.
- [ ] H05 has regression coverage for the exact authorization/fencing invariant identified by GRILL-001, with no stale owner/epoch path able to commit.
- [ ] H06 has regression coverage proving HumanVerificationGate checks expected run and canonical scope, failing closed on mismatch.
- [ ] Each implementation task uses RED → GREEN → review, with independent spec and quality review.
- [ ] Independent tasks are dispatched in parallel only when their write ownership and dependencies are disjoint.
- [ ] Parent verification independently checks subagent claims, changed paths, tests, compile, diff check, and the documentation checker.
- [ ] Final status is `LOCAL_VERIFIED` or `PARTIAL`, never `PRODUCTION_READY`, `G6_APPROVED`, or live-runtime ready.

## Non-goals

- No cron or scheduler service inside Fleet.
- No worker pool, daemon, multi-host store, HA, distributed fencing, or deployment.
- No live provider, network, credential, or dispatch activation.
- No production kernel sandbox or claim that `LocalSandboxRunner` is one.
- No direct implementation of Hermes `delegate_task` inside the Fleet core.
- No OMH installation, runtime copy, adapter, state synchronization, or Kanban integration.
- No automatic merge, push, release, deploy, or gateway restart.

## Architecture boundary

```text
PD Core
  goal → discovery → SPEC/PLAN → gates → verification → delivery decision

PD Fleet
  TaskSpec → DAG/waves → ready/claim → lifecycle/lease → report/evidence → reconcile

Hermes Runtime Host
  sessions → delegate_task → providers/models → tools/cron/capabilities

Runtime Adapter (future seam)
  Fleet envelope ↔ Hermes execution result

OMH
  reference material only; no authority
```

## Success criteria

A local simulated run can be planned, validated, claimed, executed, reconciled, and reported without external side effects. Dependency invalidation, stale ownership, and mismatched human authorization fail closed. The repository documentation no longer implies that local Fleet verification is production readiness.

## External-effect policy

This scope is read-only/local except for repository-local code, tests, documentation, and artifacts explicitly listed by a task. No network, credentials, subprocess provider, dispatch live, push, merge, deploy, or service restart is authorized.
