# Releasing

Release tags use the `vX.Y.Z` form and must match `VERSION` exactly. Pushing a
matching tag runs the release workflow, which reruns the repository checks and
publishes the source archive plus its SHA-256 checksum.

## Preflight

Run the local preflight before creating a tag:

```bash
./scripts/release_preflight.sh
```

It runs the same gates as CI/release:

| Gate | What it catches |
|---|---|
| `pytest tests -q` | Behavioral regressions |
| `flake8 scripts/ --config=.flake8` | Syntax, undefined names, unused code |
| `scripts/validate.sh` | Invalid skill frontmatter and structure |
| `tests/test_validate.sh` | Recursive validator discovery regressions |
| `tests/test_install.sh` | Installer ownership/cleanup regressions |
| `tests/test_release.sh` | Non-deterministic or malformed release archive |
| `scripts/check_markdown_links.py` | Broken relative links and anchors |
| `scripts/pd_fleet/v2_doc_paths.py` | Invalid V2 documentation paths |
| shell syntax pass | Broken `.sh` files before execution |

The Markdown-link step is the same script used by both GitHub workflows, so the
local result and the runner result cannot drift.

After creating the tag locally, run the stricter mode:

```bash
./scripts/release_preflight.sh --release
```

It additionally requires a clean working tree, no `## [Unreleased]` section, and
`v<VERSION>` pointing at `HEAD`.

Before tagging, also confirm that the latest CI matrix run for the target commit
is green. The preflight uses the local Python (3.12 in the reference environment)
and the release workflow uses a single Python, so a 3.10/3.11-only failure can
still appear after a successful release. The `v1.4.0`/`v1.4.1` pair is the worked
example of that gap.

## Release checklist

1. Rename `## [Unreleased]` in `CHANGELOG.md` to `## [X.Y.Z] - YYYY-MM-DD` and add
   the new row to the version-history table.
2. Set `VERSION` to `X.Y.Z` (no surrounding whitespace is required).
3. Commit the release changes.
4. Run `./scripts/release_preflight.sh` and fix anything it reports.
5. Create the tag: `git tag vX.Y.Z`.
6. Run `./scripts/release_preflight.sh --release`.
7. Push both refs: `git push origin main vX.Y.Z`.
8. Watch the workflow with `gh run watch <run-id> --exit-status`, then verify the
   published release with `gh release view vX.Y.Z --json tagName,assets,body`.
   Require the `.tar.gz` and `.sha256` assets and non-empty notes.

## If a release workflow fails

Never move or delete a failed release tag. Preserve it, add a changelog section
that names the failure and the fix, bump the patch version, and publish the next
tag. The `v1.3.0` → `v1.3.1` → `v1.3.2` → `v1.3.3` chain is the worked example:
each failed tag remained intact while the fix-forward release carried the fix.

A tag is not proof of a release: only a successful workflow plus the expected
assets and notes is.
