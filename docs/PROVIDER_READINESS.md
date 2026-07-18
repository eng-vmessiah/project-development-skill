# Provider readiness

Readiness probes are **read-only** checks. They do not auto-login, submit model
prompts, or make model calls. Authentication is reported only on an exact,
provider-specific signal; arbitrary success text and error messages are ignored.

| Runtime | Fixed command | Authentication signal |
|---|---|---|
| Hermes / `openai-codex` | `hermes auth status openai-codex` | A normalized line exactly equal to `openai-codex: logged in` |
| Codex CLI | `codex login status` | A normalized line exactly equal to `Logged in using ChatGPT` |
| OpenCode Go | `opencode providers list` | A normalized line containing both `OpenCode Go` and `credential` |
| Claude Code | `claude auth status --json` | JSON object with `loggedIn` whose value is exactly boolean `true` |

## Execution limits and statuses

The real local runner uses an absolute, resolved regular executable, `shell=False`,
a new process group, closed stdin, and a minimal empty environment. Output from
stdout and stderr is read incrementally with an exactly 4 KiB combined hard cap
(4096 bytes total across both streams). Exceeding the cap kills the entire process group and returns
`output_limit`; it is not authentication evidence. Timeouts kill the entire
process group, wait for it, and return `timeout`. Other launch/non-zero failures
return `failed`; a missing or invalid executable returns `not_installed`.

Captured diagnostics are discarded after parsing and are never included in the
readiness result (the legacy ``output`` field is always empty). Callers must inject explicit authentication evidence for the
separate capability-gated version probe; version output never proves login.
