# B15a.5 — Runtime Readiness Packet

**Status:** `PLANNED_READ_ONLY`  
**Current evidence:** `LOCAL_SEAM_COMPOSED`, `LOCAL_PLUGIN_DISCOVERY_VERIFIED`  
**Runtime state:** `LIVE_NOT_READY`

## Purpose

Define the authorization and operational gates required before any future local Hermes plugin installation, configuration, discovery, or activation canary. This packet authorizes none of those effects.

## Boundary

The current `pd-fleet-hermes` plugin is lifecycle-only. It does not register the Fleet D1 bridge or any Fleet RPC. A runtime plugin-discovery canary can prove only manifest validation, discovery/loading, and absence of unintended surface; it cannot prove a functioning Fleet RPC integration.

## Required new authorization

A future authorization must name: target isolated `HERMES_HOME`/profile, artifact commit/hash, plugin source, config file and exact allow-list change, operator, window, rollback owner, stop criteria, and permitted process/session command. It must separately authorize config changes, staged installation/discovery, process start, and rollback. D7 does not authorize any of these effects.

## Preconditions

- Canonical/worktree commits and clean status captured.
- Staged artifact has `integration_contract` exactly `pd-fleet`, `1.0`, `default_enabled: false`.
- Plugin is standalone, has no tools/RPC/middleware/commands, and is absent or disabled at baseline.
- Canary uses an isolated `HERMES_HOME`; no project plugin discovery and no user-plugin shadowing.
- Real host identity, default-deny capability, schema/redaction, lifecycle/recovery evidence is separately reviewed before any functional Fleet seam activation.

## Canary acceptance

A future approved canary must prove: plugin absent/disabled baseline; explicit enable only in isolated profile; real pre-import contract validation; `/plugins` confirms loaded plugin; only `on_session_start`/`on_session_end`; no tool, command, middleware, RPC, network, provider, credential, subprocess, persistence, or external side effect; clean controlled session exit; and disabled state after rollback in a fresh process.

## Stop criteria

Abort immediately for manifest/source mismatch or shadowing, failed contract validation, import/register errors, unexpected tools/RPC/commands/middleware, identity/capability/schema/redaction violation, any external effect, or inability to demonstrate rollback.

## Rollback

Stop the isolated canary process/session. Use `hermes plugins disable pd-fleet-hermes` only if explicitly authorized, then start a fresh isolated process and verify it is not loaded. Restore only the pre-captured canary configuration after a diff review. `HERMES_SAFE_MODE=1` is emergency containment for all plugins, not selective rollback.

## Non-claims

This packet does not authorize or demonstrate real Fleet RPC, session observation, Gateway transport, provider execution, messaging, durable cursor/outbox, live health, deployment, or release.
