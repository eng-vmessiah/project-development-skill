# B15a.2 Test Matrix

**Status:** `PLANNED; no live claim`

| Area | Required fixture/test | Expected evidence |
|---|---|---|
| Seam | absent, disabled, enabled, malformed config, collision, handler exception | Fleet denied/default-off; non-Fleet golden behavior unchanged |
| Identity | anonymous, forged client identity, foreign owner, missing/ambiguous binding | bounded deny; no session existence disclosure |
| Capability | missing/stale/reused activation, missing association, `fleet_owned_task` | deny without side effect |
| Wire | unknown field/enum, oversized/nested/binary/Unicode control input | bounded schema error; no mutation |
| Redaction | prompt/history/tool/provider/token/path/URL/frame fixture through all projections | sensitive keys and values absent from buffer/store/outbox/replay/log/response |
| Lifecycle | duplicate attach, reconnect, detach, session end, TUI exit, lifecycle race | one association; cleanup/revocation deterministic |
| Replay | atomic snapshot boundary, valid cursor, no-new, expired/tampered/stale/foreign cursor, gap, out-of-order/repeated/jumped sequence and boundary mismatch | ordered result or explicit bounded resync/provenance error |
| Retention/reassociation | revoke, detach, TTL expiry, ended, TUI exit and crash with old association/subscriber/epoch/cursor reuse | pre-revocation refs deny before any historical/outbox read; only fresh activate creates new refs/epoch/boundary |
| Provenance | duplicate pair, sequence/event-id conflict | idempotent duplicate or `invalid_provenance`; cursor stops |
| Recovery | each crash point in delivery contract | no silent loss/advance; recovery outcome recorded |
| Canary | fake/injected attach → event → replay → detach → cleanup | local canary only, no runtime activation |

## Future test placement

- Fleet contract/doubles: `tests/fleet/test_tui_readonly_contract.py` plus focused new tests.
- Hermes seam tests: only in separately authorized `/home/vitor/project/hermes-agent-b15a-rpc-seam` worktree.
- TUI protocol tests: only after D1–D6 and B15a.2 authorization.

Every implementation task must start RED and report separate results for contract-only, fake/injected, Hermes worktree, TUI process and live authorization. Passing local fixtures never changes `NOT_READY_HERMES_SEAM`.
