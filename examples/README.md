# Examples

Real-world examples of using Project Development Skills.

## Examples

| Example | Description | Complexity | Skills Used |
|---------|-------------|------------|-------------|
| [api-project](api-project/) | REST API with FastAPI | Medium | pd, clean-code, design-patterns, TDD, auth-patterns |
| [web-app](web-app/) | Web app with user auth | Full | pd, auth-patterns, clean-code, TDD, debugging |
| [cli-tool](cli-tool/) | Command-line CSV parser | Simple | pd, clean-code, TDD, writing-plans |

## How to Use

1. **Browse** examples for your use case
2. **Read** the `.spec/` directory to see the PD pipeline in action
3. **Follow** the README walkthrough to understand each phase
4. **Copy** relevant structure to your own project

## Example Walkthrough

### web-app (Full PD Pipeline)

This example shows the complete 8-phase pipeline:

```
examples/web-app/
├── README.md                          # Overview and walkthrough
└── .spec/user-auth/
    ├── SPEC.md                        # What we're building
    ├── PLAN.md                        # Wave-based implementation plan
    ├── STATE.md                       # Real-time progress tracking
    ├── CONTEXT.md                     # Architecture decisions (ADRs)
    ├── CHECKPOINT.md                  # Wave completion snapshot
    ├── backend/
    │   ├── 01-create-user-model.md    # Task: User model
    │   └── 02-create-auth-endpoint.md # Task: Auth endpoints
    ├── frontend/
    │   └── 01-login-form.md           # Task: Login form
    └── tests/
        └── 01-unit-tests.md           # Task: Unit tests
```

**Key files to read:**
- `SPEC.md` — How requirements are captured
- `PLAN.md` — How work is broken into waves
- `CONTEXT.md` — Architecture Decision Records (ADRs)
- Task files — Detailed implementation instructions

### cli-tool (Simplified Pipeline)

This example shows a lighter PD application:

```
examples/cli-tool/
├── README.md                          # Overview
└── .spec/csv-parser/
    ├── SPEC.md                        # Tool requirements
    ├── PLAN.md                        # 3-wave plan
    └── STATE.md                       # Progress tracking
```

**Key takeaway:** PD scales down to small projects too.

## Creating Your Own Examples

To add a new example:

1. **Create directory:** `examples/<example-name>/`
2. **Add `README.md`** with:
   - Project description
   - Skills used (table format)
   - Step-by-step walkthrough
   - Lessons learned
3. **Add `.spec/` directory** with realistic:
   - `SPEC.md` — Requirements
   - `PLAN.md` — Wave-based plan
   - `STATE.md` — Progress tracking
   - Task files — Implementation details
4. **Submit PR** with `examples:` prefix in title

### Template for New Examples

```markdown
# Example: [Project Name]

## Project Overview
[What you're building, tech stack, scope]

## Skills Used
| Skill | How It's Used |
|-------|---------------|
| **pd** | Orchestrate the pipeline |

## Pipeline Walkthrough
### Phase 1: Brainstorming
### Phase 2: Planning
### Phase 3: Coding
### Phase 4: Testing

## Key Files
- List the important files

## Lessons Learned
- What worked well
- What to watch out for
```

## Related Documentation

- [CREATING-SKILLS.md](../docs/CREATING-SKILLS.md) — How to author new skills
- [ARCHITECTURE.md](../docs/ARCHITECTURE.md) — System design decisions
- [PHILOSOPHY.md](../PHILOSOPHY.md) — Core principles
