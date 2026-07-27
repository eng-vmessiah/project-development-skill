# Multi-Platform Skill Development

Workflow for creating, validating, and distributing skills across Hermes Agent, OpenCode, and Claude Code.

## Source and platform contracts

The repository is the canonical source. Installed copies are generated deployment artifacts and must not become an undocumented second source of truth.

| Platform | Location | Deployment contract |
|---|---|---|
| Hermes | `~/.hermes/skills/<category>/<skill>/` | Complete tree: `SKILL.md`, `references/`, `templates/`, and scripts |
| OpenCode | `~/.config/opencode/skills/<skill>/` | Complete tree, with only `metadata.hermes` removed from `SKILL.md` |
| Claude | `~/.claude/commands/<skill>.md` | Flat, self-contained command rendering without `metadata.hermes` |

A Claude command cannot assume sibling `references/` files. The canonical `SKILL.md` must therefore contain the core workflow without making optional references mandatory. Directory-based platforms receive the detailed references.

## Installer requirements

A reproducible installer must:

1. copy the complete tree to Hermes;
2. copy the complete tree to OpenCode, then apply only the documented frontmatter transformation;
3. render the self-contained `SKILL.md` to Claude's flat command path, removing optional `references/` pointers from that rendering;
4. preserve relative category paths for Hermes/OpenCode so nested skills do not overwrite one another;
5. fail before copying when two source skills would collide in Claude's flat namespace;
6. remove stale files belonging to the same skill before copying, so deleted references do not survive from an older installation;
7. fail on copy or transformation errors;
8. never copy credentials, runtime state, or project artifacts.

The repository `install.sh` implements this contract for Unix-like hosts. Windows-native installations should use the same source/transform rules through an equivalent PowerShell wrapper rather than maintaining a separate hand-edited skill.

## Validation requirements

For each destination, verify:

- expected frontmatter and platform transformation;
- complete tree equality for Hermes/OpenCode except the allowed metadata difference;
- no unresolved required references in the Claude rendering;
- no stale files after reinstall;
- the actual platform loader can discover the skill.

Do not claim synchronization from a comparison of `SKILL.md` alone.

## External repositories

When synthesizing a skill from an external repository:

1. inspect the pinned revision and license;
2. read the README and relevant implementation;
3. identify reusable patterns rather than copying implementation;
4. rewrite in the skill's own words;
5. record attribution when required;
6. keep project-specific paths, names, credentials, and historical commands out of the reusable skill.

## Skill size

Keep the primary `SKILL.md` focused on routing, mandatory gates, safety rules, and the minimal executable workflow. Move domain-specific procedures and long examples to `references/`.

| Size | Guidance |
|---|---|
| `<15k` | Preferred for the primary skill |
| `15–25k` | Review for extraction into references |
| `>25k` | Split before distribution |

## Repository structure

```text
project-name/
├── README.md
├── CONTRIBUTING.md
├── LICENSE
├── install.sh
├── scripts/
└── skills/
    └── <skill-name>/
        ├── SKILL.md
        ├── references/  (optional)
        └── templates/   (optional)
```

## Common pitfalls

1. Copying only `SKILL.md` to a directory-based platform.
2. Linking mandatory behavior from a reference unavailable to Claude.
3. Removing metadata but leaving stale references/templates from an older version.
4. Treating an installed copy as canonical without auditing it.
5. Mixing project-specific examples into reusable guidance.
6. Validating only file hashes while ignoring the actual platform loader.
