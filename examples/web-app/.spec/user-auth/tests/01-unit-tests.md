# Task: Unit Tests

**Status:** `pending`
**Depends:** #01-create-user-model (partial), #02-create-auth-endpoint (full)
**Estimated:** 20 min
**Wave:** 4 — Testing

## Objective

Write comprehensive unit and integration tests for the authentication system.

## Acceptance Criteria

- [ ] Unit tests for `hash_password` and `verify_password`
- [ ] Unit tests for `create_access_token` and `decode_token`
- [ ] Integration tests for POST /auth/register
- [ ] Integration tests for POST /auth/login
- [ ] Integration tests for GET /auth/me
- [ ] Edge case tests (duplicate email, wrong password, expired token)
- [ ] Test coverage ≥ 90% on auth module

## Implementation Notes

```python
# tests/test_auth_utils.py
import pytest
from backend.auth.utils import (
    hash_password, verify_password,
    create_access_token, decode_token
)

class TestPasswordHashing:
    def test_hash_password_returns_string(self):
        hashed = hash_password("mypassword")
        assert isinstance(hashed, str)
        assert hashed != "mypassword"  # Never stores plaintext
    
    def test_verify_password_correct(self):
        hashed = hash_password("mypassword")
        assert verify_password("mypassword", hashed) is True
    
    def test_verify_password_incorrect(self):
        hashed = hash_password("mypassword")
        assert verify_password("wrongpassword", hashed) is False
    
    def test_different_hashes_for_same_password(self):
        h1 = hash_password("mypassword")
        h2 = hash_password("mypassword")
        # bcrypt uses random salt — hashes should differ
        # (but verify correctly against both)
        assert h1 != h2
        assert verify_password("mypassword", h1)
        assert verify_password("mypassword", h2)

class TestJWT:
    def test_create_and_decode_token(self):
        token = create_access_token({"sub": "user-123"})
        payload = decode_token(token)
        assert payload is not None
        assert payload["sub"] == "user-123"
        assert "exp" in payload
    
    def test_decode_invalid_token(self):
        payload = decode_token("invalid.token.here")
        assert payload is None
    
    def test_decode_expired_token(self):
        # Create a token with 0 expiry (immediately expired)
        from datetime import datetime, timedelta
        from jose import jwt
        from backend.auth.utils import SECRET_KEY, ALGORITHM
        
        token = jwt.encode(
            {"sub": "user-123", "exp": datetime.utcnow() - timedelta(hours=1)},
            SECRET_KEY,
            algorithm=ALGORITHM
        )
        payload = decode_token(token)
        assert payload is None
```

```python
# tests/test_auth_endpoints.py
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.main import app
from backend.database import Base, get_db

# Setup test database
SQLALCHEMY_TEST_DATABASE_URL = "sqlite:///./test.db"
engine = create_engine(SQLALCHEMY_TEST_DATABASE_URL)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db

@pytest.fixture(autouse=True)
def setup_database():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)

client = TestClient(app)

class TestRegistration:
    def test_register_success(self):
        response = client.post("/auth/register", json={
            "email": "test@example.com",
            "password": "secure123"
        })
        assert response.status_code == 201
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
    
    def test_register_duplicate_email(self):
        client.post("/auth/register", json={
            "email": "test@example.com",
            "password": "secure123"
        })
        response = client.post("/auth/register", json={
            "email": "test@example.com",
            "password": "another123"
        })
        assert response.status_code == 400
    
    def test_register_weak_password(self):
        response = client.post("/auth/register", json={
            "email": "test@example.com",
            "password": "short"
        })
        assert response.status_code == 422  # Validation error
    
    def test_register_no_number_in_password(self):
        response = client.post("/auth/register", json={
            "email": "test@example.com",
            "password": "noumberhere"
        })
        assert response.status_code == 422

class TestLogin:
    def test_login_success(self):
        # Register first
        client.post("/auth/register", json={
            "email": "test@example.com",
            "password": "secure123"
        })
        # Then login
        response = client.post("/auth/login", json={
            "email": "test@example.com",
            "password": "secure123"
        })
        assert response.status_code == 200
        assert "access_token" in response.json()
    
    def test_login_wrong_password(self):
        client.post("/auth/register", json={
            "email": "test@example.com",
            "password": "secure123"
        })
        response = client.post("/auth/login", json={
            "email": "test@example.com",
            "password": "wrongpassword"
        })
        assert response.status_code == 401
    
    def test_login_nonexistent_user(self):
        response = client.post("/auth/login", json={
            "email": "nonexistent@example.com",
            "password": "secure123"
        })
        assert response.status_code == 401

class TestProfile:
    def test_get_profile_authenticated(self):
        # Register and get token
        reg = client.post("/auth/register", json={
            "email": "test@example.com",
            "password": "secure123"
        })
        token = reg.json()["access_token"]
        
        # Get profile
        response = client.get("/auth/me", headers={
            "Authorization": f"Bearer {token}"
        })
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == "test@example.com"
        assert "hashed_password" not in data  # Never expose
    
    def test_get_profile_no_token(self):
        response = client.get("/auth/me")
        assert response.status_code == 401
    
    def test_get_profile_invalid_token(self):
        response = client.get("/auth/me", headers={
            "Authorization": "Bearer invalid.token.here"
        })
        assert response.status_code == 401
```

### Test Organization

```
tests/
├── conftest.py              # Shared fixtures
├── test_auth_utils.py       # Unit tests for auth utilities
├── test_auth_endpoints.py   # Integration tests for API
└── test_auth_models.py      # Model tests (optional)
```

### Running Tests

```bash
# Run all auth tests
pytest tests/test_auth_* -v

# Run with coverage
pytest tests/test_auth_* --cov=backend/auth --cov-report=html

# Run specific test class
pytest tests/test_auth_endpoints.py::TestRegistration -v
```

### Coverage Target

| Module | Target | Notes |
|--------|--------|-------|
| auth/utils.py | 100% | Critical security code |
| auth/router.py | 90%+ | API endpoints |
| auth/dependencies.py | 95%+ | Token validation |
| models/user.py | 80%+ | Model behavior |

## References

- `skills/test-driven-development/SKILL.md` — TDD patterns
- `skills/ai-regression-testing/SKILL.md` — AI testing patterns
- pytest documentation
- FastAPI testing guide
