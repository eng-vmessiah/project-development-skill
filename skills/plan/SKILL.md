---
name: plan
description: "Bomb-proof plan mode: write an actionable markdown plan, no execution. Bite-sized tasks, exact paths, complete code."
version: 2.1.0
author: ISIS (adapted from mattpocock/skills writing-great-skills)
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [planning, plan-mode, bomb-proof, workflow, design]
    related_skills: [writing-plans, subagent-driven-development, test-driven-development, requesting-code-review]
argument-hint: "What needs a bomb-proof plan?"
---

# Plan Mode

**Leading word: bomb-proof** — consistent with writing-plans. A plan so thorough no implementer has to guess. But here: plan only, no execution.

**Completion criterion:** A `.md` file saved at `.hermes/plans/` with goal, approach, step-by-step tasks, file paths, and verification steps — nothing implemented yet.

## Core behavior

For this turn, you are planning only.

- Do not implement code.
- Do not edit project files except the plan markdown file.
- Do not run mutating terminal commands, commit, push, or perform external actions.
- You may inspect the repo or other context with read-only commands/tools when needed.
- Your deliverable is a markdown plan saved inside the active workspace under `.hermes/plans/`.

## Output requirements

Write a markdown plan that is concrete and actionable.

Include, when relevant:
- Goal
- Current context / assumptions
- Proposed approach
- Step-by-step plan
- Files likely to change
- Tests / validation
- Risks, tradeoffs, and open questions

If the task is code-related, include exact file paths, likely test targets, and verification steps.

## Save location

Save the plan with `write_file` under:
- `.hermes/plans/YYYY-MM-DD_HHMMSS-<slug>.md`

Treat that as relative to the active working directory / backend workspace. Hermes file tools are backend-aware, so using this relative path keeps the plan with the workspace on local, docker, ssh, modal, and daytona backends.

If the runtime provides a specific target path, use that exact path.
If not, create a sensible timestamped filename yourself under `.hermes/plans/`.

## Interaction style

- If the request is clear enough, write the plan directly.
- If no explicit instruction accompanies `/plan`, infer the task from the current conversation context.
- If it is genuinely underspecified, ask a brief clarifying question instead of guessing.
- After saving the plan, reply briefly with what you planned and the saved path.

---

# Crafting the Plan Content

The craft of writing a bomb-proof plan — bite-sized tasks, complete code, exact paths — lives in the **`writing-plans`** skill. Load it for the full reference: leading word "bomb-proof", completion criteria per step, TDD-oriented task structure, and verification checklist.

**Key points from writing-plans to apply here:**
- Each task = 2-5 minutes of focused work
- Include exact file paths (not "the config file" but `src/config/settings.py`)
- Include complete code examples (copy-pasteable)
- Include exact commands with expected output
- Write tasks in order: setup → core → edge cases → integration → cleanup

## Remember

```markdown
Bite-sized tasks (2-5 min each)
Exact file paths
Complete code (copy-pasteable)
Exact commands with expected output
Verification steps
DRY, YAGNI, TDD
Frequent commits
```

**A good plan makes implementation obvious.**
