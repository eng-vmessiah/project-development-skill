# Templates

Standardized templates for project documentation.

## Overview

Templates ensure consistent documentation across projects. They are stored in `skills/pd/templates/` and copied during installation.

## Available Templates

### TASK.md

Used for individual task definitions.

```markdown
# Task: [Task Name]

## ID
TASK-XXX

## Status
[ ] Pending
[ ] In Progress
[ ] Done

## Description
Brief description of the task.

## Acceptance Criteria
- [ ] Criterion 1
- [ ] Criterion 2
- [ ] Criterion 3

## Dependencies
- TASK-XXX (depends on)

## Time Estimate
[X] hours

## Notes
Additional notes...
```

### CHECKPOINT.md

Used for progress tracking.

```markdown
# Checkpoint: [Date]

## Progress
- Tasks completed: X/Y
- Current phase: [Phase]
- Blockers: [None/List]

## Completed Tasks
- [x] TASK-001: Description
- [x] TASK-002: Description

## Next Steps
- [ ] TASK-003: Description
- [ ] TASK-004: Description

## Issues
- Issue 1: Description and resolution

## Time Spent
[X] hours total
```

### STATUS.md

Used for project status overview.

```markdown
# Project Status: [Project Name]

## Summary
Brief project status summary.

## Phase
Current phase: [Phase Name]

## Progress
| Metric | Value |
|--------|-------|
| Tasks | X/Y complete |
| Tests | X passing |
| Coverage | X% |
| Blockers | X |

## Recent Changes
- Change 1
- Change 2

## Next Milestones
- Milestone 1: [Date]
- Milestone 2: [Date]

## Risks
- Risk 1: Mitigation
- Risk 2: Mitigation
```

## Usage

### Automatic (via pd)

When using the pd skill, templates are automatically available:

```
.spec/01-feature/
├── TASK-001-setup.md      # From TASK.md template
├── CHECKPOINT-2024-01.md  # From CHECKPOINT.md template
└── STATUS.md              # From STATUS.md template
```

### Manual

Copy templates to your project:

```bash
# Copy templates
cp skills/pd/templates/* .spec/.templates/

# Use in your project
cp .spec/.templates/TASK.md .spec/01-feature/TASK-001.md
```

## Customization

### Creating New Templates

1. Create template file: `skills/pd/templates/MY-TEMPLATE.md`
2. Follow existing format
3. Add header with template name
4. Submit PR

### Modifying Templates

1. Edit template in `skills/pd/templates/`
2. Update documentation
3. Submit PR

## Best Practices

### When to Use Each Template

| Template | Use When |
|----------|----------|
| TASK.md | Defining a single unit of work |
| CHECKPOINT.md | Tracking progress (daily/weekly) |
| STATUS.md | Reporting to stakeholders |

### Naming Conventions

```
TASK-001-setup.md
TASK-002-model.md
CHECKPOINT-2024-01-15.md
STATUS.md (one per project)
```

### Tips

- Keep tasks small (1-4 hours)
- Update checkpoints regularly
- STATUS.md should be executive-friendly
- Use checkboxes for tracking
