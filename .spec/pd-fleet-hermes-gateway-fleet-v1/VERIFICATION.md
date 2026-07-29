# Gateway Fleet Bridge — Verification

**Status:** `pending`
**Scope:** discovery/design only

This file will record G0–G8 evidence. No verification claim is made until the corresponding gate has fresh evidence.

## Current baseline

- Existing Hermes Gateway/dashboard source inspected read-only.
- Existing PD Fleet v0 fake-only contract preserved.
- No Hermes process, provider, network, credential, configuration, or live Gateway activated.
- No runtime implementation authorized.

## Required evidence before G8

- source/file references for Gateway surface and event semantics;
- user-owned versus Fleet-owned ownership matrix;
- versioned bridge/event contract;
- cursor/replay/reconnect tests;
- injected observer harness tests;
- capability and redaction review;
- documentation checker output;
- `git diff --check` output;
- independent spec/compliance and security/quality review;
- explicit human decision for any implementation or local canary.
