# Example: Web Application with User Authentication

This example demonstrates the full PD pipeline applied to a realistic web application feature: **user authentication** for a task management app.

## Project Overview

**App:** TaskFlow — a simple project management tool
**Stack:** Python (FastAPI) + React + PostgreSQL
**Feature:** User authentication (register, login, profile management)

## Skills Used

| Skill | How It's Used |
|-------|---------------|
| **pd** | Orchestrates the full 8-phase pipeline |
| **auth-patterns** | JWT implementation, password hashing, session management |
| **clean-code** | Maintainable Python and TypeScript code |
| **test-driven-development** | Tests written before implementation |
| **systematic-debugging** | Debugging auth flow issues |

## Pipeline Walkthrough

### Phase 1: Brainstorming

The team discusses requirements with the AI:
- What authentication method? → JWT (stateless, scalable)
- Password hashing? → bcrypt via passlib
- Email verification? → Deferred to Phase 2
- OAuth providers? → No, email/password only for MVP

**Output:** Raw ideas and decisions captured in CONTEXT.md

### Phase 2: Planning (.spec/)

SPEC.md defines what we're building. PLAN.md breaks it into waves:

```
Wave 1: Backend Foundation
  → Create User model
  → Setup password hashing
  → Create auth utilities

Wave 2: Auth Endpoints
  → POST /auth/register
  → POST /auth/login
  → GET /auth/me

Wave 3: Frontend
  → Login form component
  → Registration form component
  → Auth context and protected routes

Wave 4: Testing
  → Unit tests for auth utilities
  → Integration tests for endpoints
  → Frontend component tests
```

### Phase 3: Structure (.templates/)

Each task gets a file under `.spec/user-auth/`:
```
.spec/user-auth/
├── SPEC.md           # What we're building
├── PLAN.md           # How we're building it (waves)
├── STATE.md          # Current progress
├── CONTEXT.md        # Key decisions and rationale
├── CHECKPOINT.md     # Progress snapshot
├── backend/
│   ├── 01-create-user-model.md
│   └── 02-create-auth-endpoint.md
├── frontend/
│   └── 01-login-form.md
└── tests/
    └── 01-unit-tests.md
```

### Phase 4: Coding (Wave-Based)

Tasks are executed in waves. Each wave produces a checkpoint:

**Wave 1 Result:**
```python
# backend/models/user.py
from sqlalchemy import Column, String, DateTime
from sqlalchemy.sql import func
import uuid

class User(Base):
    __tablename__ = "users"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String, unique=True, nullable=False, index=True)
    hashed_password = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
```

**Wave 2 Result:**
```python
# backend/auth/router.py
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/register")
def register(user: UserCreate, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == user.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")
    hashed = hash_password(user.password)
    new_user = User(email=user.email, hashed_password=hashed)
    db.add(new_user)
    db.commit()
    return {"access_token": create_token(new_user.id)}
```

### Phase 5: Testing

Tests written following TDD principles:
- Unit tests for `hash_password` and `verify_password`
- Integration tests for registration and login endpoints
- Edge cases: duplicate email, wrong password, expired token

### Phase 6: Validation

Evidence-based verification:
- All tests passing
- Code review checklist complete
- Security review (no plaintext passwords, proper error messages)

## Key Files

- `SPEC.md` — Feature requirements
- `PLAN.md` — Wave-based implementation plan
- `STATE.md` — Real-time progress tracking
- `CONTEXT.md` — Design decisions and rationale
- Task files — Detailed instructions for each implementation step
- `CHECKPOINT.md` — Wave completion snapshots

## Lessons Learned

1. **Start with the model** — Auth flows are data-driven; the User model shapes everything
2. **Separate concerns early** — Keep auth logic out of route handlers
3. **Test the unhappy path** — Most auth bugs come from edge cases
4. **Checkpoint after each wave** — Makes resuming easier if context is lost
