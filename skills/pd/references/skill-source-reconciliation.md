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
8. Verify expected platform transformations only (for example, metadata removal), and verify hashes/content for all other files.

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
- Do not claim synchronization until all active destinations have been reinstalled and checked.
