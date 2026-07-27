# Security Hardening Wave — Reusable Recipe

Use this reference when PD is applied to a personal agent bridge, local API, WebSocket terminal, or messaging gateway.

## Read-only reconnaissance

Dispatch independent fresh agents before implementation:

- REST/WS boundary: enumerate public routes, protected routes, handshake timing, fail-open conditions.
- Integration: inspect frontend WebSocket construction, HTTP clients, reverse proxies, systemd units, bind addresses.
- Policy/operations: inspect Discord/channel/role allowlists, administrative actions, rollback, restart, logs.
- Test design: build deterministic offline RED/GREEN and smoke matrix.

No agent in this wave edits files or restarts services.

## Critical probes

```bash
python -m py_compile <auth-and-entrypoint-files>
git status --short --branch
systemctl --user cat <unit>
ss -ltnp | grep -E ':(<port>)\\b'
curl -i http://127.0.0.1:<port>/health
curl -i http://127.0.0.1:<port>/<protected-route>
```

When inspecting source via a redacting tool, independently run syntax/import checks before declaring corruption. Redacted environment access such as `os.getenv(...)` can appear truncated while remaining valid.

## Authentication contract checklist

- Health/liveness exceptions are exact matches, not broad `startswith` bypasses.
- Missing credentials fail closed in production; local development bypass requires an explicit flag.
- HTTP protected routes reject missing and invalid credentials with `401`.
- WebSockets authenticate before `accept()` and reject invalid connections with a policy failure.
- Validate WebSocket `Origin`; CORS does not protect WebSocket handshakes.
- Bind session/resource resume IDs to the authenticated principal.
- Never place a permanent API key in a WebSocket query string.
- Prefer HttpOnly session cookies for browser clients, or short-lived single-use tickets as an interim design.
- Separate terminal/shell capability from ordinary read/chat access.

## Gateway policy checklist

Prefer scoped exceptions over global permissiveness:

- explicit user allowlist;
- explicit channel allowlist;
- main channel may be free-response/no-thread if desired;
- keep global mention requirement enabled elsewhere;
- restrict server actions to read-only by default;
- do not use `ALLOW_ALL_USERS=true` as a compatibility shortcut;
- retain a redacted backup and test rollback.

## Test matrix

At minimum:

1. public health remains `200`;
2. protected REST is `401` without credentials and `200` with a test credential;
3. WS agent and terminal reject anonymous handshakes before acceptance;
4. authenticated WS chat/ping still works with mocked provider;
5. terminal blocklist behavior remains covered, while documenting that a blocklist is not a sandbox;
6. allowed CORS origin succeeds and arbitrary origin does not;
7. docs/OpenAPI follow an explicit exposure policy and contain no secrets;
8. service binds to the intended interface;
9. restart returns to healthy state;
10. logs do not contain credentials.

Keep these tests offline. Existing provider/OAuth failures must be isolated from the hardening gate, not hidden by conditional skips.

## Stop conditions

Pause before implementation if:

- authentication architecture is undecided;
- a proposed change could lock out the owner;
- active uncommitted WIP overlaps target files;
- the subagent reports conflict with live state;
- rollback cannot be demonstrated.
