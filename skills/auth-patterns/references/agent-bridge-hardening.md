# Agent-bridge hardening reference

Concrete companion for the `the agent bridge Hardening` section in `SKILL.md`. Keep secrets, real Origins, user IDs, tokens, and provider credentials out of this file.

## Browser bootstrap pattern

Use a same-origin server-side proxy when a browser UI must bootstrap an HttpOnly session from an API-key-protected bridge:

1. Browser calls `POST /api/auth/session/bootstrap` with `credentials: "include"` and no API key.
2. Vite/server proxy forwards the request to the bridge and injects `Authorization: Bearer ${process.env.BRIDGE_API_KEY}` in the server process only.
3. Bridge validates the Bearer key and sets an opaque `HttpOnly; Secure; SameSite=Strict` cookie.
4. Mount/gate the React application until bootstrap succeeds; ordinary same-origin fetches and WebSockets then use the cookie automatically.
5. Never put the API key in `VITE_*`, static JavaScript, query strings, WebSocket URLs, localStorage, or sessionStorage.

The proxy must inject the credential only for the exact bootstrap route, fail closed when the server environment lacks the key, and keep the bridge target server-side. In systemd, prefer an `EnvironmentFile` with restrictive permissions over embedding a secret in `ExecStart`.

## Vite proxy shape

```ts
proxy: {
  '/api': {
    target: 'http://127.0.0.1:18005',
    changeOrigin: true,
    configure(proxy) {
      proxy.on('proxyReq', (_proxyReq, req) => {
        if (req.url === '/api/auth/session/bootstrap') {
          const key = process.env.BRIDGE_API_KEY;
          if (!key) return; // backend must reject; do not fabricate auth
          _proxyReq.setHeader('Authorization', `Bearer ${key}`);
        }
      });
    },
  },
  '/ws': { target: 'ws://127.0.0.1:18005', ws: true },
}
```

Use exact-path matching rather than injecting the key into every proxied request. If the development server is exposed beyond loopback, treat its environment and host binding as a security boundary.

## CORS and documentation

- Reuse the same exact Origin allowlist for WebSocket Origin checks and `CORSMiddleware`; do not maintain two drifting lists.
- Use explicit methods and headers. Avoid `allow_methods=['*']` and `allow_headers=['*']` when credentials are enabled.
- Disable public `/docs`, `/redoc`, and `/openapi.json` unless an authenticated documentation path is deliberately implemented.
- Test both an allowed and untrusted Origin, including preflight behavior where relevant.

## Offline test matrix

Focused tests should cover:

- missing API-key configuration rejects protected HTTP and WebSocket requests;
- bootstrap accepts only a valid Bearer credential;
- cookie flags include HttpOnly, Secure, SameSite=Strict, and bounded max age;
- logout immediately invalidates the protected route and removes the session from the store;
- cookie-authenticated mutating requests require an allowed Origin; Bearer clients remain usable;
- WebSockets reject missing/invalid Origin and credentials before `accept()`;
- terminal WebSocket rejects sessions without `bridge:terminal`;
- `resume` cannot cross authenticated session ownership;
- docs/OpenAPI endpoints are unavailable and untrusted CORS Origins receive no allow-origin header.

When the application lifespan initializes external providers, use an isolated ASGI/CORS wrapper or deterministic local database fixture for security tests. Do not weaken the authentication assertion just to make provider-dependent tests pass. Run focused tests first, then the complete suite and classify external OAuth/provider failures separately.

## Operational sequencing

1. Validate backend and frontend builds without restarting the live service.
2. Confirm the frontend can bootstrap and open WebSockets through the proxy.
3. Change the Bridge unit to `127.0.0.1` and prepare rollback.
4. Only after the hardened code is integrated into the deployed worktree: run `daemon-reload`, restart, smoke-test health/auth/WS, and verify the listening socket.
5. Do not claim the bind hardening is active while the old process still listens on `0.0.0.0`.

The session store is process-local unless explicitly backed by shared storage; document the single-worker/restart limitation and do not imply multi-worker durability.