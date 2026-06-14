# Roadmap

This document outlines the development roadmap for Project Development Skills.

## Current State: v1.0.0

**Released:** 2026-06-14

The initial release includes 17 skills, a CLI tool, templates, and multi-platform installer support.

| Category | Skills | Status |
|----------|--------|--------|
| Core Pipeline | `pd` (master orchestrator) | ✅ Stable |
| Code Quality | `clean-code`, `ddd-development`, `design-patterns` | ✅ Stable |
| Authentication | `auth-patterns` | ✅ Stable |
| Testing | `test-driven-development`, `ai-regression-testing` | ✅ Stable |
| AI Integration | `ai-optimization`, `ai-regression-testing` | ✅ Stable |
| Debugging | `systematic-debugging` | ✅ Stable |
| Writing | `humanizer`, `writing-clearly-and-concisely`, `writing-plans` | ✅ Stable |
| Architecture | `service-composition` | ✅ Stable |
| Workflow | `plan`, `spike`, `subagent-driven-development`, `requesting-code-review` | ✅ Stable |

**Infrastructure:**
- Multi-platform installer (Hermes Agent, OpenCode, Claude Code)
- CLI tool (`scripts/pd`) with commands: `init`, `status`, `validate`, `checkpoint`
- Templates: `TASK.md`, `CHECKPOINT.md`, `STATUS.md`
- Test suite with pytest
- CI/CD pipeline with GitHub Actions

---

## Phase 1: Foundation (Current) ✅

**Goal:** Ship a solid, usable skill ecosystem with the core pipeline working end-to-end.

### Completed
- [x] Master `pd` skill with 8-phase pipeline
- [x] 17 skills covering code quality, patterns, testing, AI, writing, and workflow
- [x] Multi-platform installer supporting Hermes, OpenCode, and Claude Code
- [x] CLI tool (`scripts/pd`) with basic commands
- [x] Templates for tasks, checkpoints, and status
- [x] Test suite with pytest
- [x] CI/CD pipeline with GitHub Actions
- [x] Documentation: README, CONTRIBUTING, CHANGELOG, PHILOSOPHY
- [x] Example: REST API with FastAPI
- [x] Code review skill for pre-commit verification

### In Progress
- [ ] Comprehensive example coverage (web-app, cli-tool)
- [ ] CI/CD artifact collection for test results
- [ ] Skill validation script

---

## Phase 2: Expansion (Next)

**Goal:** Add specialized skills for common development domains.

### New Skills

| Skill | Description | Priority |
|-------|-------------|----------|
| **api-design** | REST/GraphQL API design patterns, versioning, documentation | High |
| **database-patterns** | Schema design, migrations, indexing, query optimization | High |
| **security-checklist** | OWASP Top 10, dependency scanning, secrets management | High |
| **monitoring-observability** | Logging, metrics, tracing, alerting setup | Medium |
| **recipes** | Common solutions for recurring problems (beyond GoF patterns) | Medium |
| **performance-patterns** | Profiling, caching, lazy loading, connection pooling | Medium |
| **documentation-patterns** | API docs, README structure, architecture decision records | Medium |
| **deployment-patterns** | CI/CD strategies, blue-green, canary, feature flags | Medium |

### Enhancements
- [ ] Cross-skill recommendations (e.g., `pd` suggests `api-design` for REST work)
- [ ] Skill composition guides (which skills work together for common projects)
- [ ] Performance benchmarks for the CLI tool
- [ ] Plugin hooks for custom skill extensions

### Milestones
- **v1.1.0** — `api-design` + `database-patterns` + enhanced examples
- **v1.2.0** — `security-checklist` + `monitoring-observability`
- **v1.3.0** — `recipes` + `performance-patterns` + `documentation-patterns`
- **v1.4.0** — `deployment-patterns` + skill composition guides

---

## Phase 3: Ecosystem (Future)

**Goal:** Build an extensible platform for community contributions and IDE integration.

### IDE Extensions
- **VS Code extension** — Inline skill suggestions based on file context
- **JetBrains plugin** — Integration with IntelliJ-based IDEs
- **Vim/Neovim** — LSP-style integration for terminal users

### Plugin System
- Custom skill authoring framework
- Skill registry (discover and share community skills)
- Versioned skill dependencies
- Runtime validation of skill interactions

### Community
- Contribution rewards for high-quality skills
- Skill review process (curated registry)
- Example bounties for underrepresented domains (mobile, embedded, game dev)
- Integration with popular project templates (Vite, Next.js, FastAPI, etc.)

### Advanced Features
- AI-powered skill recommendation based on project analysis
- Automated `.spec/` generation from natural language descriptions
- Cross-project learning (patterns that worked on similar codebases)
- Integration with project management tools (Linear, Jira, GitHub Projects)

---

## Known Issues and Limitations

### Current
1. **CLI tool is read-only** — `pd` CLI can validate and show status, but cannot yet create/modify `.spec/` files programmatically
2. **No automatic cross-references** — Skills don't automatically link to related skills in output
3. **Template rigidity** — Templates are fixed; no custom field support yet
4. **No incremental updates** — Running `pd` replays the full pipeline; no resume from last checkpoint
5. **Skill size** — Some skills exceed 15k tokens; could benefit from modularity
6. **Limited examples** — Only one comprehensive example (REST API); needs more diversity

### Planned Fixes
- CLI v2 with file creation commands (v1.1.0)
- Custom template support (v1.2.0)
- Checkpoint resume functionality (v1.2.0)
- Skill splitting for large files (v1.3.0)
- IDE integration for live suggestions (Phase 3)

---

## How to Contribute

### Adding a New Skill
1. Read `docs/CREATING-SKILLS.md` for authoring guidelines
2. Follow the skill template structure (see existing skills)
3. Include: Overview, When to Use, Quick Reference, Core Patterns, Anti-Patterns, Common Mistakes, Decision Trees
4. Write tests if the skill includes executable components
5. Add examples showing the skill in action
6. Submit PR with `skill:` prefix in title

### Improving Existing Skills
1. Check open issues for `skill:` labels
2. Follow the same structure and tone
3. Keep additions focused — one concern per skill file
4. Update the CHANGELOG

### Adding Examples
1. Create directory: `examples/<example-name>/`
2. Include `.spec/` directory with realistic SPEC.md, PLAN.md, STATE.md
3. Show the PD pipeline phases in action
4. README.md with walkthrough and skills used

### Code Contributions
- Bug fixes welcome anytime
- New features should be discussed in issues first
- All changes require tests where applicable
- CI must pass before merge

---

## Versioning Strategy

This project follows [Semantic Versioning](https://semver.org/):

```
MAJOR.MINOR.PATCH
```

| Change Type | Version Bump | Example |
|-------------|-------------|---------|
| New skills, breaking skill changes | MINOR | 1.0.0 → 1.1.0 |
| Bug fixes, docs, examples | PATCH | 1.0.0 → 1.0.1 |
| Breaking CLI changes, plugin system | MAJOR | 1.x → 2.0.0 |

### Release Process
1. Update CHANGELOG.md with changes
2. Create git tag: `git tag v1.X.Y`
3. GitHub Actions runs tests on tag
4. Release notes auto-generated from CHANGELOG

### Supported Platforms
- **Hermes Agent** — Primary platform, full support
- **OpenCode** — Full support, tested in CI
- **Claude Code** — Community maintained, best-effort support

---

## Timeline

```
2026-Q2: v1.0.0 (released) — 17 skills + CLI
2026-Q3: v1.1.0 — api-design, database-patterns, enhanced examples
2026-Q3: v1.2.0 — security, monitoring, custom templates
2026-Q4: v1.3.0 — recipes, performance, documentation patterns
2026-Q4: v1.4.0 — deployment patterns, skill composition
2027-Q1: v2.0.0 — Plugin system, IDE extensions, community registry
```

---

*This roadmap is a living document. Priorities may shift based on community feedback and contributions.*
