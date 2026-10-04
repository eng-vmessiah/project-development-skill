# B15a.2 — Evidence Packet (Fase 1 closeout)

- **Status:** `LOCAL_SEAM_VERIFIED / LIVE_NOT_READY`
- **Date:** 2026-10-04
- **Scope:** D7 authorization — local / default-off / read-only; worktree-isolated; no install, no runtime activation, no provider/network/credentials, no session mutation, no push/merge/release.
- **Series:** S0 (integration branch + gap analysis) → S1–S5 implemented; S6 = independent dual review + this packet.
- **Commits:**
  - Hermes (`~/project/hermes-agent-b15a2-integration`, branch `feat/b15a2-integration`, unpushed): `1828ab35dd` (S1 codec) · `df1fc55f0a` (S2 service) · `a2412badf6` (S3 registration) · `0e3ac7915d` (S4 hooks) · `759fe1bd73` (S5 refactor) · `590a18f75f` (S6 fixes).
  - PD (`~/project/project-development-skill`, branch `feat/b15a2-host-integration`): `d9c6afd` (gap analysis) · `f7b466a` (harness) · `[S6]` (this packet + harness updates + STATE).
  - S0 series worktrees: `hermes-agent-b15a-seam-v2` @ `e98c30490b` (4 commits, 31 passed + 4 contracts); `hermes-agent-fleet-observer-v2` @ `d501af7a68` (10 commits, fleet 120 passed).

## Independent review (S6)

Two reviewers in fresh contexts, read-only, running all suites themselves.

**Verdicts (security/invariants):** client-authority `holds`; redaction `holds with caveat` (denylist is a heuristic but unreachable from client input — the only client string is the HMAC-verified cursor); sequence continuity `holds with caveat` (two mapping defects, fixed below); default-off `holds with caveat` (funnel performs one suppressed no-op import on first close); no-runtime-effects `holds`.

### Findings & disposition

| # | Severity | Finding | Disposition |
|---|---|---|---|
| 1 | major | Replay responses over the 8 KiB envelope raised internal `payload_too_large`, escaping the handler as -32000 — a dead-end retry loop for backlogs beyond ~31 events | **FIXED** (`590a18f75f`): bounded pagination — largest fitting prefix + advancing `next_cursor`; `payload_too_large` is now a canonical `ERROR_CODES` member. Tests: `test_replay_paginates_bounded_batches` (worktree), `test_replay_paginates_large_backlog_end_to_end` (harness) |
| 2 | major | End hook carried no session identity → association pinned when the resolver moved on; a close of an unrelated session could end the wrong association | **FIXED** (`590a18f75f`): `session_ref` flows funnel → hooks → service; unrelated/invalid refs are no-ops. Tests: `test_session_ended_targets_named_session`, `test_session_ended_ignores_unrelated_or_invalid_refs`, `test_close_funnel_passes_session_identity` |
| 3 | minor | `hmac.compare_digest` on `str` raised TypeError for non-ASCII MAC parts (raw error instead of bounded canonical) | **FIXED**: byte comparison. Test: `test_replay_non_ascii_cursor_fails_closed` |
| 4 | minor | A hub-first expiry check (diverging clocks) mapped to `replay_gap` instead of `cursor_expired` | **FIXED**: closed-message mapping. Test: `test_replay_hub_clock_expiry_maps_to_cursor_expired` |
| 5 | minor | Uncovered branches: reachable `payload_too_large` path, non-ASCII cursor, session-change-before-end; expiry/gap only in the PD harness | **ADDRESSED**: +8 worktree tests (78 total); expiry and gap now also in-worktree |
| 6 | medium | S4 feeds only `session.ended` (+ `registered`/`detached` at attach/deactivate); `note_status` has no host caller; heartbeat/metadata producers not wired | **ACCEPTED LIMITATION** (documented; `note_status` stays API-ready; real host transitions are a D4 semantics decision for the owner — no telemetry fabrication) |
| 7 | medium | G4 §9 wrong owner/profile/workspace: owner covered; profile/workspace not representable at this layer (binding carries no such fields) | **ACCEPTED LIMITATION** (documented; needs a contract decision) |
| 8 | low | Concurrent-duplicate evidence is RLock serialization, not a lock-free race proof | **DOCUMENTED** (harness docstring + here) |
| 9 | low | No timing-budget assertion for uniform failures (G4 §6) | **OPEN** (live-phase item for Fase 2/3) |
| 10 | low | Non-Fleet golden weak (one unknown method, dict equality) | **STRENGTHENED**: serialized-JSON stability check; full transcript golden deferred |
| 11 | low | Harness docstring overclaimed end-to-end for the wrong-observer fixture | **FIXED**: fixture now goes through adapter + dispatch |
| 12 | low | "Revoked" fixture is owner deactivation; revoked-ticket covered at registry level only (by design — clients never present tickets) | **DOCUMENTED** (bucketed) |
| 13 | low | Invalid flag values untested at the registration seam | **FIXED**: `test_invalid_flag_values_are_rejected_fail_closed` |
| 14 | nit | Denylist heuristic (leetspeak-evadable); dead branches (`_MAX_SESSIONS`, `result.gap`); one import on first close | **ACCEPTED/DOCUMENTED** (unreachable from client input; defensive code kept) |

### Corrected overclaims (wording now pinned)

- S4 wires `session.ended` (all close paths incl. TUI exit) + `registered`/`detached` at attach/deactivate — status/heartbeat/metadata producers are NOT wired (finding 6).
- Concurrency: lock-serialized idempotency, not lock-free atomicity.
- Funnel "byte-for-byte": exact return semantics + one suppressed no-op call.
- Crash/restart: evidenced as restart-secret cursor invalidation + registry one-shot/epoch tests; crash-before/after-consume fixtures are NOT at the wire (partial).
- PD bridge: batch-acceptance canary only — its handlers are not-ready stubs; the wire ops are served by the host-side handlers.

## Buckets (per gap doc §8)

| Bucket | Artifacts | Result |
|---|---|---|
| contract-only | S1 codec suite `tests/hermes_cli/test_fleet_tui_wire.py` (26) | PASS |
| fake/injected (host) | S2/S3/S4 suites: session 22, registration 8, hooks 9, seam 13 (+ wire 26 = **78 total**) | PASS |
| TUI-process (host-path) | funnel tests incl. the rebound-copy runtime path (`test_close_funnel_via_server_rebound_copy`) | PASS |
| Hermes-seam (local) | PD harness `tests/fleet/test_b15a2_host_seam_harness.py` (12) — pinned command below | PASS |
| live-authorization | none — live link deferred by design | `NOT_READY` (unchanged) |

**Pinned harness command** (skip-mode caveat: without this PYTHONPATH the whole file skips — a green PD-only run proves nothing):

```
cd ~/project/project-development-skill && env -u PYTHONPATH \
  PYTHONPATH=/home/vitor/project/hermes-agent-b15a2-integration \
  /home/vitor/project/hermes-agent-fleet-observer-v2/.venv/bin/python -m pytest \
  tests/fleet/test_b15a2_host_seam_harness.py -q -p no:cacheprovider
```

Result: **12 passed** (includes the pagination e2e added in S6).

## §8 evidence mapping (item → named evidence → observed)

| Item | Named evidence | Observed |
|---|---|---|
| absent configuration | `test_plugin_rpc_seam.py::test_plugin_rpc_registration_is_disabled_by_default` (+ batch variant) | PASS — -32601 |
| disabled configuration | `test_fleet_tui_registration.py::test_registration_is_default_off`; `test_fleet_tui_hooks.py::test_funnel_noop_without_hooks`, `::test_hooks_registry_defaults_and_type_gate` | PASS |
| enabled configuration | `test_enabled_registration_is_atomic_and_dispatches_all_four`; harness `test_real_adapter_binds_real_host_and_dispatches_wire` | PASS — four names atomic, all ops dispatch |
| invalid configuration | `test_service_requires_ready_owner_and_enabled_hub`; observer-config rejections; **NEW** `test_invalid_flag_values_are_rejected_fail_closed` | PASS (flag values now covered) |
| foreign owner / wrong observer | harness `test_wrong_observer_owner_is_denied` (via adapter+dispatch); `test_activate_denied_when_context_owner_mismatches` | PASS — `observer_not_authorized` |
| wrong owner/profile/workspace | owner: covered (above). profile/workspace: **not representable** at this layer | PARTIAL (documented, finding 7) |
| ambiguous identity | nearest: `test_activate_denied_when_identity_unresolved`; ambiguity as such | MISSING (fail-closed path exists; noted) |
| duplicate attach (incl. concurrent) | harness `test_duplicate_presentation_is_idempotent_reconnect`, `test_concurrent_duplicate_presentation`; `test_activate_is_idempotent_on_reconnect`, `test_single_active_session_enforced` | PASS — one association (lock-serialized) |
| invalid cursor | harness `test_malformed_requests_fail_closed`; `test_replay_cursor_tamper_fails_closed`, **NEW** `test_replay_non_ascii_cursor_fails_closed` | PASS — `invalid_request`/`invalid_provenance` |
| expired cursor | harness `test_expired_cursor_fails_closed`; **NEW** `test_replay_cursor_expiry_fails_closed`, `test_replay_hub_clock_expiry_maps_to_cursor_expired` | PASS — `cursor_expired` |
| stale cursor | harness `test_cross_scope_cursor_is_rejected`; `test_replay_cursor_scope_binding` | PASS — `cursor_stale` |
| replay gap | harness `test_replay_gap_after_retention_eviction`; observer `test_retention_ttl_controls_cursor_and_replay_gap_deterministically` | PASS — deterministic fake clocks |
| crash/restart | `test_restart_invalidates_old_cursors`; activation one-shot/epoch tests | PARTIAL (restart + epoch; crash windows not at wire) |
| redaction escape attempts | wire `test_refs_reject_sensitive_or_malformed_values`, `test_event_envelope_is_closed`, `test_event_payload_bounds_and_redaction`; observer allowlist tests | PASS |
| non-Fleet golden | `test_non_fleet_dispatch_is_unchanged` (serialized-stable) + collision tests | PASS (strengthened; full transcript deferred) |
| no session-existence disclosure | harness `test_no_session_existence_disclosure` | PASS (code/shape indistinguishable; timing budget open) |
| pagination / large backlog | **NEW** `test_replay_paginates_bounded_batches`; harness `test_replay_paginates_large_backlog_end_to_end` | PASS |

## G4 §9 negative fixtures (mapped to the wire)

| Fixture | Evidence | Result |
|---|---|---|
| valid first presentation | `test_real_adapter_binds_real_host_and_dispatches_wire` | PASS |
| duplicate presentation | `test_duplicate_presentation_is_idempotent_reconnect` | PASS (reconnect, never duplicate attach) |
| concurrent duplicate presentation | `test_concurrent_duplicate_presentation` | PASS (RLock-serialized; see finding 8) |
| wrong observer | `test_wrong_observer_owner_is_denied` (via dispatch) | PASS |
| wrong owner/profile/workspace | owner PASS; profile/workspace not representable (finding 7) | PARTIAL |
| wrong session/association | `test_cross_scope_cursor_is_rejected`, `test_session_ended_ignores_unrelated_or_invalid_refs` | PASS |
| wrong purpose | not representable at this layer (no client purpose input; server-resolved) | N/A (by construction) |
| expired ticket | cursor-expiry variants (ticket expiry at registry level: activation suite) | PASS (bucketed) |
| revoked ticket | owner deactivation at wire (`test_revoked_owner_denies_reactivation`); revoked-ticket at registry level | PASS (bucketed, finding 12) |
| malformed/unknown ticket | `test_malformed_requests_fail_closed` | PASS |
| crash before/after consume; restart with uncertain consumption | restart-secret + epoch/one-shot tests only | PARTIAL (crash windows deferred) |
| no session-existence disclosure on failure | `test_no_session_existence_disclosure` | PASS (timing budget open) |

## Non-Fleet compatibility & default-off

- Fleet methods unregistered → -32601 (absent/disabled); registration requires explicit `enabled is True` (invalid flags fail closed).
- Non-Fleet dispatch serialized-stable across registration (strengthened golden).
- No production call site for `register_fleet_session_rpcs` / `set_fleet_tui_hooks` (grep-verified) — default-off end-to-end.
- Funnel keeps exact return semantics; one suppressed no-op call per close when disabled (documented caveat).

## Canonical regression (host repo)

`bash scripts/run_tests.sh tests/tui_gateway/ -j 4` (canonical per-file runner — monolithic pytest is unsupported and aborts):

- **Post-fix: 267 files, 2344 passed, 93 failed (24 files) — failed list byte-identical to the pre-fix run (24×24 files, 93=93 tests).** The +2 passed are the two new S6 tests in this tree.
- Two load-sensitive flakes appeared across runs (`test_change_watcher_sessions.py` pre-fix, `test_default_profile_session_name.py` post-fix); both pass in isolation (5/5 and 3/3) and on the merge-base baseline (3/3), and the runner retries and passes them (FLAKY classification — not counted as failures).
- Pre-existing environment failures (93 tests / 24 files + 1 collection error `test_ephemeral_profile_override.py`) are identical to the merge-base baseline. No new failures introduced by S1–S6.

## Explicit non-claims

- No live Hermes link, no install, no activation, no provider/network/credentials — `NOT_READY_HERMES_SEAM` remains.
- `local_verified` never replaces live authorization; Fase 2 (canary) and Fase 3 (install/activation) require a **new explicit authorization** (B15A5-style runtime readiness packet).
- No merge/push/release performed; all work is local in worktrees.
