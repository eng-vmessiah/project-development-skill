# Read-only reconciliation CLI

Use this reference when a CLI compares an existing durable snapshot/run store with an append-only event log.

## Contract

- Reuse existing source contracts and a thin library/Supervisor facade before adding CLI serialization.
- Do not create a second persistence authority or index until the existing store has been audited.
- Distinguish these states explicitly: both sources absent, snapshot absent, log absent, existing empty log, valid consistent sources, divergent sources, and corrupt sources.
- Emit a bounded immutable report; JSON should be the report's exact `to_dict()` shape, while text is a deterministic bounded projection.

## Strict read-only preflight

1. Validate IDs, limits, epochs, and path types before constructing source readers.
2. Inspect every existing path component with `lstat`; reject symlinks and non-directory roots. Never call `resolve()` before this validation.
3. Do not instantiate a store whose constructor creates directories, lock files, or other scaffolding when the requested root is absent.
4. Do not use cleanup to undo a read-side effect. A later `unlink`/`rmdir` can delete content created by another process during a race.
5. For an absent source, produce the same bounded report through a no-write helper; for existing sources, delegate to the canonical reconciliation facade.
6. When replay returns an empty collection, inspect the already-supplied log path with safe metadata: an absent file and an existing empty regular file are different states.

## Required probes

- subprocess through the real CLI entrypoint;
- both roots absent, one root absent, empty log, non-empty log;
- divergent sequence/count and corrupt inputs;
- root symlink and nested-component symlink;
- non-directory root;
- race-created content proving the command never deletes it;
- bytes and mtimes before/after;
- no feature discovery, project `STATE`, dispatch, provider, network, or subprocess side effects;
- parser/help and all advertised shell completions (record unavailable shell runtimes as environment-limited, not as PASS).

## Closeout

Run focused tests, the full suite, compile/static checks, a real subprocess probe, and fresh-eyes review. A green suite alone does not prove read-only behavior; the filesystem and symlink/race probes are part of the acceptance contract.
