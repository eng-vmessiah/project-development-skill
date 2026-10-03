# Skill Source Reconciliation

Use this when a skill repository and one or more installed copies disagree.

## Canonical-source rule

Treat the versioned repository as the intended source of truth and installed paths as deployment artifacts. However, do not overwrite a richer installed copy before auditing it: it may contain uncommitted improvements, platform-specific transformations, or environment-specific additions.

## Reconciliation sequence

1. Inventory every copy: repository, active Hermes profile, other Hermes profiles, OpenCode, Claude, and any symlink targets.
2. Compare hashes, line counts, mtimes, directory contents, references, templates, and scripts.
3. Inspect Git branches, remotes, reflogs, and worktrees in the source repository before concluding that work is missing.
4. Compare installed-only content semantically. Classify each item as generic reusable guidance, platform adapter, project-specific guidance, duplicate, or stale material.
5. Make a backup of every installed copy before changing it.
6. Promote accepted installed-only improvements into a reconciliation branch in the source repository. Do not silently edit the active installation as the first step.
7. Commit the reconciled source, then reinstall all destinations from that source.
8. Immediately before each install, re-snapshot the destination and compare its hash/content with the audited backup. If it changed during reconciliation, stop and re-audit the new copy instead of overwriting it.
9. Verify expected platform transformations only (for example, metadata removal), and verify hashes/content for all other files.
10. If an additional destination is discovered after the first inventory (for example, a flat Claude command), back it up first, then classify its format and include it in the post-install matrix.
11. Stage the installer against temporary Hermes/OpenCode/Claude destinations before touching active installations. Assert that nested references/templates/scripts are copied, platform-specific rendering is correct, stale files are removed only within the managed skill scope, and flat-name collisions fail closed.
12. Keep the active runtime unchanged until the staged install and verification matrix pass; a validated installer is not the same as a completed live synchronization.

## Required report

Record:

- canonical source path and commit;
- every installation path and active profile;
- ahead/behind or worktree evidence;
- installed-only files and accepted/rejected classification;
- backup paths;
- source commit containing the reconciliation;
- post-install verification results.

## Pitfalls

- A larger installed `SKILL.md` is evidence of additional content, not proof that it is canonical or correct.
- Do not compare only the main file; missing `references/` can be the real divergence.
- Do not assume the default Hermes profile is synchronized with named profiles.
- Do not use a generic installer that copies only `SKILL.md` when the skill depends on `references/`, `templates/`, or `scripts/`.
- Backups and reports must record paths, hashes, and classifications without preserving or printing credentials, tokens, or other secrets; redact sensitive values.
- A destination that changes during the audit is not a harmless race: treat the latest content as a new source candidate and preserve both snapshots before deciding.
- A late-discovered flat-format installation must be handled separately; do not assume every platform uses the same directory tree or frontmatter.
