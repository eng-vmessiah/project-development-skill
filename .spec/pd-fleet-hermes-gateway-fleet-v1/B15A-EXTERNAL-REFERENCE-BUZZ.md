# B15a External Reference — Block Buzz

**Source:** `https://github.com/block/buzz`  
**Snapshot audited:** `28ae6cd` (2026-08-02)  
**License observed:** Apache-2.0  
**Evidence level:** source/documentation review; no runtime, relay, dependency or harness installation.

## Verdict

| Dimension | Verdict |
|---|---|
| Architectural relevance | `HIGH` |
| Direct dependency adoption | `REJECT` |
| B15a implementation dependency | `NONE` |
| Future reference | `ADOPT_PATTERNS_ONLY` |

Buzz is a self-hosted workspace/relay and ACP harness ecosystem. Hermes remains this project's runtime/capability/policy owner; Buzz is not a replacement runtime or required control plane.

## Observed facts

- `buzz-acp` bridges relay events to ACP/JSON-RPC agents including Goose, Codex and Claude Code.
- Its remote-agent design separates desktop, provider, substrate, agent and relay.
- It documents fail-closed identity, presence-as-status, at-most-one live instance and terminal intentional shutdown.
- Provider output is hostile; deploy provider protocol is narrow and payloads are bounded/redacted.
- It explicitly distinguishes conversational presence from substrate/process health.
- MCP lifecycle hooks are opt-in, bounded by timeout/rejection budgets and not exposed as model-controlled hooks.

## Adopt

| Pattern | Receiving layer | Decision |
|---|---|---|
| Identity is independent of launcher/harness/substrate | B15a D2/D3 | Preserve server-derived identity and default-deny intersection |
| Presence/status is not runtime health | B15a D5/D6 readiness language | Report scope-specific status; never infer live health |
| Closed, hostile-by-default protocol boundary | B15a D4/D5 | Preserve schema, bounds, redaction, issuer-bound cursor and provenance checks |
| Explicit lifecycle/revocation/retention | B15a D6 | Preserve fresh reassociation and tombstone/purge semantics |
| Harness adapter as a narrow boundary | Future B15c | Design adapter contract after Hermes local seam proof |

## Adapt later — B15c Harness Adapter Contract

**Precondition:** B15a reaches `LOCAL_SEAM_VERIFIED`; no B15c work is implied by this note.

Candidate interface, read-only first:

```text
HarnessAdapter
  describe_capabilities()
  inspect_readonly()
  subscribe_bounded()
  replay_bounded()
  detach()
```

Rules:

- Hermes stays authoritative for policy/capability/identity.
- An ACP adapter may support Claude Code, Codex, Goose or another compatible harness, but does not gain Fleet dispatch authority.
- Each adapter must independently satisfy identity, capability, bounded schema/redaction, lifecycle, replay/provenance and cleanup contracts.
- Runtime-specific capability claims must remain explicit; no inferred parity.

## Adoption boundary

Buzz is reference-only: use it to evaluate architectural choices, naming, threat models, lifecycle matrices and test ideas. Do not copy or port its source code, import it as a depe...[truncated]

- Do not install or depend on Buzz, Nostr relay, `buzz-acp`, Kubernetes providers or remote-agent components.
- Do not create a parallel control plane or identity system.
- Do not treat presence as proof of Hermes process health.
- Do not expose MCP lifecycle hooks or ACP harnesses as Fleet execution/control surfaces.
- Do not add remote deployment, secrets, provider binaries or subprocess management to B15a.

## Revisit gate

Revisit B15c only after local seam evidence, independent review, and a separate approval packet. Any ACP spike must be isolated, fake/injected first, default-off and have a rollback boundary.
