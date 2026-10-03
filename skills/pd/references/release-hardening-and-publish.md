# Release hardening and publish checklist

Use this class-level procedure when a user authorizes a project to ship beyond local verification.

## Scope and gates

1. Reconcile the current branch against the actual `main` and remote state. Record exact SHA, ancestry, dirty paths, worktrees, and tags.
2. Separate four states: implementation complete, locally verified, package/release-ready, and operationally ready. Provider/live execution, deployment, sandbox, and human approval gates must not be inferred from unit tests.
3. Inventory distribution contracts: installer destinations, nested resources, CLI/runtime files, stale-file cleanup, ownership manifests, collision behavior, and clean-home smoke tests.
4. Turn CI into executable contracts: canonical tests, recursive validators, shell syntax, static checks, docs/link checks, installer tests, and artifact tests. Avoid claiming repository-wide lint if only a scoped subset is checked; document the scope.

## TDD and independent review

- For each security or portability finding, reproduce RED with the smallest adversarial test before changing code.
- Implement the narrow root-cause fix, then run focused tests, full suite, static/diff checks, and a fresh-eyes review.
- Treat delegated reports as leads. Independently inspect diffs, exact files, commit ancestry, and command output.
- When CI fails after local green, read the exact hosted log. Reproduce the cause instead of rerunning blindly. Filesystem metadata and timing assumptions commonly differ between local and hosted runners.

## Versioning and artifacts

- Use one authoritative `VERSION` file and derive tag/archive/checksum names from it.
- Build a reproducible source archive from the exact tag (`git archive`, deterministic gzip) and publish a SHA-256 sidecar.
- The release workflow must verify `tag == v$VERSION` before testing or publishing.
- Do not rewrite an already-pushed tag after a failed workflow. Fix forward with a patch release (for example `1.1.1`) and preserve the failed tag's provenance.
- Verify the published release externally: run status, non-draft/non-prerelease state, asset names, downloaded checksum, and archive contents.

## Integration and closeout

- Integrate release work into the current `main` with an explicit conflict-resolution step that preserves both branch intents; use fast-forward integration where possible.
- Rerun the full gate suite on the exact `main` commit intended for the tag, then push branch/main/tag only after explicit delivery authorization.
- Final report must include commit, tag, workflow run, release URL, asset/checksum evidence, test count, and explicit deferred operational scope.
- Write a durable session summary after delivery. Keep `implemented`, `verified`, `review pending`, `deferred`, and `blocked` separate.
