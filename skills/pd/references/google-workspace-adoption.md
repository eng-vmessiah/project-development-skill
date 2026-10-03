# Google Workspace Integration — Reusable Adoption Notes

## Decision pattern

For a local, single-user product that may connect multiple Gmail/Calendar accounts, do not implement OAuth token storage and refresh first. Compare:

- **Official Google Workspace CLI (`googleworkspace/cli`)**: covers Gmail/Calendar and OAuth, emits JSON, supports a configurable config directory, and stores encrypted credentials through its credential backend. Best initial adapter for a local product.
- **Nango**: self-hostable OAuth/token/connection manager with multi-tenant support. Better when the product becomes a multi-user SaaS; heavier operationally and has license/adoption considerations.
- **Composio/Activepieces**: broad agent/workflow platforms; generally overkill and introduce more external surface area for a narrow local Gmail/Calendar need.

Architectural relevance is not adoption readiness. Prefer the official CLI adapter for the first local slice, while keeping the product's domain independent of CLI syntax.

## Account isolation pattern

Store only account metadata in the product database:

```text
google_accounts
├── id
├── email
├── display_name
├── config_dir
├── scopes
├── status
└── last_used_at
```

Keep credentials in a separate config directory per account:

```text
$JOB_HUNTER_DATA_DIR/google/<account-id>/gws-config
```

For each invocation, set:

```bash
GOOGLE_WORKSPACE_CLI_CONFIG_DIR="$JOB_HUNTER_DATA_DIR/google/<account-id>/gws-config"
```

This enables runtime account switching without changing `.env`, restarting the application, or sharing a global assistant token directory. Never put tokens in source control, logs, agent prompts, generated candidate packages, or the domain database when the adapter already owns encrypted credential storage.

## Safe implementation boundary

The product should own:

- `GoogleAccount` validation and account IDs;
- SQLite metadata registry and status;
- list/select/disconnect operations;
- account-to-application/candidacy association;
- policy and human approval gates;
- audit events and domain contracts.

The adapter should own:

- OAuth login and callback mechanics;
- token refresh and encrypted credential storage;
- provider CLI/API translation.

The first product slice should expose only read-only methods such as Gmail message listing/search and Calendar event listing. Compose/send and event mutation require separate scopes and approval/idempotency/audit work.

## Verification recipe

1. Install the official CLI in an isolated/user-controlled way and record the version.
2. Run `gws auth status` with a temporary project config directory, not the default global directory.
3. Confirm the status output points only to the temporary/project directory and reports no credentials before OAuth.
4. Unit-test command construction, environment isolation, timeout, nonzero exit, and invalid JSON using a mocked subprocess.
5. Use an additive migration for account metadata and assert the schema has no `refresh_token` column.
6. Test register/list/select/disconnect for at least two distinct account config directories.
7. Keep OAuth/real Gmail/Calendar verification as a separate gate requiring an authorized OAuth Client and test user.

## MVP rule

Provider authentication is optional. The local MVP must continue to work offline without Gmail/Calendar credentials. Mark OAuth and live API work `deferred`, not `blocked`, when the offline adapter seam and tests are green. Do not mark the provider gate complete until a real authorized probe succeeds.

## Session evidence captured

- `gws 0.22.5` installed and `gws --version` succeeded.
- With `GOOGLE_WORKSPACE_CLI_CONFIG_DIR=<temporary-dir>`, `gws auth status` reported `auth_method: none`, no credentials, and paths inside the temporary directory; it did not use `~/.hermes`.
- The Job Hunter adapter was tested with project-scoped config dirs, SQLite metadata-only migration, safe subprocess/JSON handling, and read-only Gmail/Calendar contracts.
- The implementation remained offline and no Google account was authenticated.
