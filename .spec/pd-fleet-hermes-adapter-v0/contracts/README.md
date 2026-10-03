# Adapter v0 Contract Fixtures

These JSON fixtures are the normative G0.2 review bundle. They are local test data only; they do not authorize dispatch or provider execution.

## Format

The bundle separates three layers:

1. **Wire request:** the strict per-operation envelope validated by `schema.json`.
2. **Wire result/entity:** bounded public output validated by `result-schema.json`.
3. **Review fixture:** local scenario data containing request fields plus expected assertions or hostile test descriptions. Fixture metadata is never sent to the adapter.

The current fixtures remain JSON scenario artifacts; validation extracts their request projection and validates it against `schema.json`. Result fixtures, when present, validate independently against `result-schema.json`.

- `schema_version`: always `pd-fleet-hermes-adapter:v0`.
- IDs are lowercase safe slugs, max 128 UTF-8 bytes.
- Mutating requests carry complete lineage, `owner`, `expected_generation`, `idempotency_key`, and a SHA-256 `request_fingerprint`.
- `session_handle_id` is opaque fake correlation only.
- `root_ref` is a non-sensitive test reference; absolute paths, traversal and control characters are forbidden.
- Expected failures expose only stable `error_code` values.

## Operation classes

| Operation | Mutating | Dispatch allowed |
|---|---:|---:|
| `prepare` | yes | no |
| `execute` | yes | fake only in G2+ |
| `observe` | no | no |
| `cancel` | yes | no |
| `handoff` | yes | no |
| `cleanup` | yes | no |

## Fixture index

The manifest is authoritative and must reference every fixture. Current coverage:

- `schema.json`: machine-readable JSON Schema for all six operation request envelopes; validators must resolve refs locally and never fetch URLs.
- `valid-prepare.json`: complete lineage and non-dispatching preparation.
- `invalid-owner.json`, `stale-fencing.json`, `stale-handle.json`, `invalid-lineage-workspace.json`: owner/lineage/generation fencing.
- `replay-conflict.json`, `replay-same-fingerprint.json`, `replay-concurrent-reservation.json`, `replay-terminal-tombstone.json`: idempotency/replay.
- `cancel-confirmed.json`, `cancel-not-confirmed.json`: termination confirmation.
- `cleanup-failure.json`: terminal preservation after cleanup failure.
- `observe-read-only.json`: bounded read-only observation.
- `handoff-forbidden-fields.json`: handoff privacy rejection.
- `hostile-inputs.json`, `workspace-invalid.json`: fail-closed hostile input and workspace cases.
- `redaction-before-fingerprint.json`: canonical redacted bytes and reproducible digest.
- `no-dispatch-boundary.json`: fake-only policy boundary; executable reachability evidence remains a G2/G3 implementation artifact and is not claimed here.

A fixture is not implementation evidence. G1 reviews the contract; G2 authorizes fake implementation; G3 verifies the implemented boundary.