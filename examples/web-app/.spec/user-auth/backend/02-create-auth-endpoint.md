# Task: Create Auth Endpoints

**Status:** `in_progress`
**Depends:** #01-create-user-model
**Estimated:** 30 min
**Wave:** 2 — Auth Endpoints

## Objective

Implement the three authentication endpoints: register, login, and get current user profile.

## Acceptance Criteria

### Registration (POST /auth/register)
- [ ] Accepts email + password in request body
- [ ] Validates email format
- [ ] Validates password strength (min 8 chars, 1 number)
- [ ] Returns 400 if email already registered
- [ ] Hashes password with bcrypt before storage
- [ ] Returns JWT access token on success
- [ ] Returns 201 status code on success

### Login (POST /auth/login)
- [ ] Accepts email + password via OAuth2 form or JSON body
- [ ] Returns 401 for invalid credentials
- [ ] Verifies password with bcrypt
- [ ] Returns JWT access token on success
- [ ] Includes token type and expiry in response

### Profile (GET /auth/me)
- [ ] Requires valid JWT in Authorization header
- [ ] Returns 401 for missing/invalid token
- [ ] Returns user profile (id, email, role, created_at)
- [ ] Never returns hashed_password

## Implementation Notes

```python
# backend/auth/router.py
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr, validator
import re

router = APIRouter(prefix="/auth", tags=["authentication"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

# --- Request/Response Models ---

class UserRegister(BaseModel):
    email: EmailStr
    password: str
    
    @validator("password")
    def validate_password(cls, v):
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        if not re.search(r"\d", v):
            raise ValueError("Password must contain at least one number")
        return v

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = 86400  # 24 hours

class UserProfile(BaseModel):
    id: str
    email: str
    role: str
    created_at: str

# --- Endpoints ---

@router.post("/register", response_model=TokenResponse, status_code=201)
def register(user: UserRegister, db: Session = Depends(get_db)):
    # Check for duplicate email
    existing = db.query(User).filter(User.email == user.email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A user with this email already exists"
        )
    
    # Create user with hashed password
    hashed = hash_password(user.password)
    new_user = User(email=user.email, hashed_password=hashed)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    # Generate token
    token = create_access_token({"sub": new_user.id})
    return TokenResponse(access_token=token)

@router.post("/login", response_model=TokenResponse)
def login(email: str, password: str, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    token = create_access_token({"sub": user.id})
    return TokenResponse(access_token=token)

@router.get("/me", response_model=UserProfile)
def get_profile(current_user: User = Depends(get_current_user)):
    return UserProfile(
        id=current_user.id,
        email=current_user.email,
        role=current_user.role,
        created_at=current_user.created_at.isoformat()
    )
```

```python
# backend/auth/utils.py
from datetime import datetime, timedelta
from passlib.context import CryptContext
from jose import jwt, JWTError
import os

SECRET_KEY = os.getenv("JWT_SECRET_KEY")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)

def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def decode_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None
```

```python
# backend/auth/dependencies.py
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from .utils import decode_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> User:
    payload = decode_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    user_id = payload.get("sub")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )
    return user
```

### Error Handling Pattern

All auth errors follow a consistent pattern:
```python
raise HTTPException(
    status_code=status.HTTP_4XX_XXXX,
    detail="Human-readable message",
    headers={"WWW-Authenticate": "Bearer"}  # Only for 401
)
```

### Security Notes
- Never log passwords or tokens
- Generic error messages (don't reveal if email exists)
- JWT secret key from environment variable only
- Token expiry enforced on every request

## Validation

After implementation, verify with curl:

```bash
# Register
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com", "password": "secure123"}'

# Login
curl -X POST http://localhost:8000/auth/login \
  -d "email=test@example.com&password=secure123"

# Profile (use token from above)
curl http://localhost:8000/auth/me \
  -H "Authorization: Bearer <token>"
```

## References

- `skills/auth-patterns/SKILL.md` — JWT implementation patterns
- `skills/clean-code/SKILL.md` — Error handling patterns
- OWASP Authentication Cheat Sheet
