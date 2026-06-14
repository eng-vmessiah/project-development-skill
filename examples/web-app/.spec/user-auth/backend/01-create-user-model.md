# Task: Create User Model

**Status:** `done`
**Depends:** — (first task)
**Estimated:** 15 min
**Wave:** 1 — Backend Foundation

## Objective

Create the SQLAlchemy User model with all required fields for authentication.

## Acceptance Criteria

- [ ] User model defined with correct columns
- [ ] UUID primary key with auto-generation
- [ ] Email field with unique constraint and index
- [ ] Hashed password field (never stores plaintext)
- [ ] created_at and updated_at timestamp fields
- [ ] Model works with SQLAlchemy async sessions
- [ ] Migration script generated

## Implementation Notes

```python
# backend/models/user.py
import uuid
from sqlalchemy import Column, String, DateTime
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import enum

class Role(str, enum.Enum):
    USER = "user"
    ADMIN = "admin"

class User(Base):
    __tablename__ = "users"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(128), nullable=False)
    role = Column(String(20), default=Role.USER)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    def __repr__(self):
        return f"<User {self.email}>"
```

### Key Decisions
- **UUID string** (not binary): easier to work with in JWTs and URLs
- **String(36)** for UUID column: fits UUID v4 format
- **No password field**: only `hashed_password` exists
- **role column with string**: simpler than enum for PostgreSQL

### Migration

```bash
alembic revision --autogenerate -m "create_users_table"
alembic upgrade head
```

### Validation

After creation, verify:
1. Can create user with valid data
2. Email uniqueness constraint works
3. Cannot store user without required fields
4. UUID is auto-generated
5. Timestamps are set automatically

## References

- `skills/clean-code/SKILL.md` — Naming conventions
- `skills/ddd-development/SKILL.md` — Entity patterns
