# Example: REST API with FastAPI

This example shows how to use the PD pipeline to build a REST API.

## Skills Used

- **pd** — Orchestrate the full pipeline
- **clean-code** — Write maintainable Python code
- **design-patterns** — Apply Factory and Strategy patterns
- **test-driven-development** — Write tests first
- **auth-patterns** — Implement JWT authentication

## Step 1: Brainstorming (Phase 1)

```
skill_view(name='pd')
# Follow Phase 1: Brainstorming
```

**Output:** `.spec/01-user-api/SPEC.md`

```markdown
# User API Specification

## Requirements
- User registration with email/password
- JWT authentication
- CRUD operations for users
- Role-based access control

## Endpoints
- POST /auth/register
- POST /auth/login
- GET /users/me
- PUT /users/me
- DELETE /users/me
- GET /users (admin only)
```

## Step 2: Planning (Phase 2)

```
# Follow Phase 2: Planning
```

**Output:** `.spec/01-user-api/PLAN.md`

```markdown
# Implementation Plan

## Wave 1: Foundation
- Task 1: Setup project structure
- Task 2: Create User model
- Task 3: Setup database

## Wave 2: Auth
- Task 4: Implement registration
- Task 5: Implement login
- Task 6: Add JWT middleware

## Wave 3: CRUD
- Task 7: Implement GET /users/me
- Task 8: Implement PUT /users/me
- Task 9: Implement DELETE /users/me

## Wave 4: Admin
- Task 10: Implement GET /users
- Task 11: Add RBAC checks
```

## Step 3: Structure (Phase 3)

**Output:** `.spec/01-user-api/`

```
.spec/01-user-api/
├── SPEC.md
├── PLAN.md
├── CONTEXT.md
├── backend/
│   ├── 01-setup.md
│   ├── 02-user-model.md
│   ├── 03-database.md
│   ├── 04-registration.md
│   ├── 05-login.md
│   └── ...
└── tests/
    ├── 01-model-tests.md
    ├── 02-auth-tests.md
    └── ...
```

## Step 4: Coding (Phase 4)

```python
# backend/models/user.py
from sqlalchemy import Column, String, Enum
from sqlalchemy.ext.declarative import declarative_base
import enum

Base = declarative_base()

class Role(str, enum.Enum):
    USER = "user"
    ADMIN = "admin"

class User(Base):
    __tablename__ = "users"
    
    id = Column(String, primary_key=True)
    email = Column(String, unique=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(Enum(Role), default=Role.USER)
```

```python
# backend/auth/jwt.py
from datetime import datetime, timedelta
from jose import jwt

SECRET_KEY = "your-secret-key"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
```

## Step 5: Testing (Phase 5)

```python
# tests/test_auth.py
import pytest
from fastapi.testclient import TestClient

def test_register_user(client):
    response = client.post("/auth/register", json={
        "email": "test@example.com",
        "password": "securepassword"
    })
    assert response.status_code == 200
    assert "access_token" in response.json()

def test_login_user(client, test_user):
    response = client.post("/auth/login", data={
        "username": test_user.email,
        "password": "password"
    })
    assert response.status_code == 200
```

## Step 6: Validation (Phase 6)

```markdown
# VERIFICATION.md

## Requirement Coverage
- [x] User registration
- [x] JWT authentication
- [x] CRUD operations
- [x] Role-based access

## Test Results
- Unit tests: 15/15 passing
- Integration tests: 8/8 passing
- Coverage: 87%

## Code Quality
- Linting: ✅ Clean
- Type hints: ✅ Present
- Docstrings: ✅ Complete
```

## Final Structure

```
my-api/
├── backend/
│   ├── models/
│   │   └── user.py
│   ├── auth/
│   │   ├── jwt.py
│   │   └── dependencies.py
│   ├── routes/
│   │   ├── auth.py
│   │   └── users.py
│   └── main.py
├── tests/
│   ├── test_auth.py
│   └── test_users.py
├── .spec/
│   └── 01-user-api/
│       ├── SPEC.md
│       ├── PLAN.md
│       └── ...
└── requirements.txt
```
