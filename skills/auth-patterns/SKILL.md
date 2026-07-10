---
name: auth-patterns
description: "Guard your API: JWT, OAuth 2.0, RBAC, sessions, and API key patterns for secure authentication and authorization."
version: 1.1.0
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [auth, security, guard, jwt, oauth, rbac, sessions]
    related_skills: [clean-code, service-composition, requesting-code-review]
argument-hint: "What needs a guard?"
---

# Auth Patterns

**Leading word: guard** — every endpoint is a door. Auth is the guard that checks credentials before letting anyone through. JWT, OAuth, sessions, API keys — they're just different uniforms the guard recognizes.

**Completion criterion:** Every protected endpoint has at least one auth guard layer, passwords are hashed (bcrypt, rounds ≥ 12), tokens expire, and the security checklist is fully checked.

## Authentication Methods

| Method | Use Case | Stateless |
|--------|----------|-----------|
| Session | Traditional web apps | No |
| JWT | APIs, SPAs | Yes |
| OAuth 2.0 | Third-party login | Depends |
| API Keys | Server-to-server | Yes |

## JWT (JSON Web Tokens)

### Structure
```
header.payload.signature

Header: { "alg": "HS256", "typ": "JWT" }
Payload: { "sub": "user123", "exp": 1234567890 }
Signature: HMACSHA256(base64(header) + "." + base64(payload), secret)
```

### Implementation (FastAPI)
```python
from datetime import datetime, timedelta
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel

# Config
SECRET_KEY = os.environ["JWT_SECRET"]
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 15
REFRESH_TOKEN_EXPIRE_DAYS = 7

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"

def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def create_refresh_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def verify_token(token: str, token_type: str = "access") -> dict | None:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != token_type:
            return None
        return payload
    except JWTError:
        return None

# Dependency
async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db)
) -> User:
    payload = verify_token(token)
    if not payload:
        raise HTTPException(
            status_code=401,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = await db.get(User, payload["sub"])
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user
```

### Endpoints
```python
@router.post("/login", response_model=Token)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db)
):
    user = await authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=401,
            detail="Incorrect username or password"
        )

    return Token(
        access_token=create_access_token({"sub": str(user.id)}),
        refresh_token=create_refresh_token({"sub": str(user.id)}),
    )

@router.post("/refresh", response_model=Token)
async def refresh(refresh_token: str, db: AsyncSession = Depends(get_db)):
    payload = verify_token(refresh_token, token_type="refresh")
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    user = await db.get(User, payload["sub"])
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    return Token(
        access_token=create_access_token({"sub": str(user.id)}),
        refresh_token=create_refresh_token({"sub": str(user.id)}),
    )

@router.post("/logout")
async def logout(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    # Add token to blacklist or invalidate refresh token
    await invalidate_user_tokens(db, current_user.id)
    return {"message": "Logged out"}
```

## OAuth 2.0

### Flows
| Flow | Use Case |
|------|----------|
| Authorization Code | Web apps with backend |
| PKCE | SPAs, mobile apps |
| Client Credentials | Machine-to-machine |

### Implementation with Authlib
```python
from authlib.integrations.starlette_client import OAuth

oauth = OAuth()
oauth.register(
    name='google',
    client_id=os.environ["GOOGLE_CLIENT_ID"],
    client_secret=os.environ["GOOGLE_CLIENT_SECRET"],
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'},
)

@router.get("/login/google")
async def login_google(request: Request):
    redirect_uri = request.url_for("auth_callback")
    return await oauth.google.authorize_redirect(request, redirect_uri)

@router.get("/callback")
async def auth_callback(request: Request, db: AsyncSession = Depends(get_db)):
    token = await oauth.google.authorize_access_token(request)
    user_info = token.get('userinfo')

    # Create or update user
    user = await get_or_create_user(db, email=user_info['email'])

    # Generate own tokens
    return Token(
        access_token=create_access_token({"sub": str(user.id)}),
        refresh_token=create_refresh_token({"sub": str(user.id)}),
    )
```

## RBAC (Role-Based Access Control)

### Model
```python
from enum import Enum
from sqlalchemy import Table, Column, ForeignKey

class Role(str, Enum):
    ADMIN = "admin"
    MANAGER = "manager"
    USER = "user"

class Permission(str, Enum):
    READ_USERS = "read:users"
    WRITE_USERS = "write:users"
    DELETE_USERS = "delete:users"
    READ_ORDERS = "read:orders"
    WRITE_ORDERS = "write:orders"

ROLE_PERMISSIONS = {
    Role.ADMIN: [p for p in Permission],
    Role.MANAGER: [
        Permission.READ_USERS,
        Permission.READ_ORDERS,
        Permission.WRITE_ORDERS,
    ],
    Role.USER: [
        Permission.READ_ORDERS,
    ],
}

# Dependency
def require_permissions(*permissions: Permission):
    async def check_permissions(
        current_user: User = Depends(get_current_user)
    ):
        user_permissions = ROLE_PERMISSIONS.get(current_user.role, [])
        for perm in permissions:
            if perm not in user_permissions:
                raise HTTPException(
                    status_code=403,
                    detail=f"Permission denied: {perm}"
                )
        return current_user
    return check_permissions

# Usage
@router.delete("/users/{user_id}")
async def delete_user(
    user_id: int,
    current_user: User = Depends(require_permissions(Permission.DELETE_USERS))
):
    # ...
```

## Session-Based Auth

```python
from starlette.middleware.sessions import SessionMiddleware

app.add_middleware(
    SessionMiddleware,
    secret_key=os.environ["SESSION_SECRET"],
    max_age=3600,  # 1 hour
    https_only=True,
    same_site="strict",
)

@router.post("/login")
async def login(request: Request, credentials: LoginRequest):
    user = await authenticate(credentials)
    if not user:
        raise HTTPException(401)

    request.session["user_id"] = str(user.id)
    request.session["created_at"] = datetime.utcnow().isoformat()
    return {"message": "Logged in"}

@router.post("/logout")
async def logout(request: Request):
    request.session.clear()
    return {"message": "Logged out"}

# Dependency
async def get_session_user(request: Request) -> User:
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(401)
    return await db.get(User, user_id)
```

## Password Security

```python
from passlib.context import CryptContext
import secrets

pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__rounds=12
)

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)

# Password reset
def generate_reset_token() -> str:
    return secrets.token_urlsafe(32)

async def request_password_reset(email: str, db: AsyncSession):
    user = await get_user_by_email(db, email)
    if not user:
        return  # Don't reveal if email exists

    token = generate_reset_token()
    expiry = datetime.utcnow() + timedelta(hours=1)

    await save_reset_token(db, user.id, token, expiry)
    await send_reset_email(email, token)
```

## API Keys

```python
import hashlib
import secrets

def generate_api_key() -> tuple[str, str]:
    """Returns (key_for_user, hash_for_db)"""
    key = secrets.token_urlsafe(32)
    key_hash = hashlib.sha256(key.encode()).hexdigest()
    return key, key_hash

async def verify_api_key(
    api_key: str = Header(..., alias="X-API-Key"),
    db: AsyncSession = Depends(get_db)
) -> User:
    key_hash = hashlib.sha256(api_key.encode()).hexdigest()
    api_key_record = await db.query(ApiKey).filter_by(key_hash=key_hash).first()

    if not api_key_record or api_key_record.revoked:
        raise HTTPException(401, "Invalid API key")

    return await db.get(User, api_key_record.user_id)
```

## Security Checklist

- [ ] Passwords hashed with bcrypt (rounds >= 12)?
- [ ] JWT with short expiration (15-30 min)?
- [ ] Refresh tokens implemented?
- [ ] Token blacklist for logout?
- [ ] Rate limiting on auth endpoints?
- [ ] HTTPS mandatory?
- [ ] Cookies with Secure, HttpOnly, SameSite?
- [ ] RBAC or granular permissions?
- [ ] Secure password reset?
- [ ] Auth event logging?

---

## Anti-Patterns

| Pattern | Problem |
|---------|---------|
| Storing JWT in localStorage | XSS vulnerability |
| Long-lived access tokens | Increased attack window |
| No rate limiting on login | Brute force attacks |
| Revealing user existence | User enumeration |
| Custom cryptography | Use established libraries |
| Storing passwords in plain text | Obvious security risk |
| No HTTPS | Man-in-the-middle attacks |

---

## Integration with Skills

### design-patterns
- **Strategy:** Swap auth methods (JWT, OAuth, Session)
- **Factory:** Create auth providers
- **Decorator:** Add auth checks to routes
- **Proxy:** Access control

### clean-code
- Single responsibility for auth functions
- Clear naming for permissions
- Explicit error handling

### security-review
- This skill provides the patterns
- security-review validates the implementation

---

## References

- OWASP Authentication Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html
- JWT.io: https://jwt.io/
- OAuth 2.0 RFC 6749: https://datatracker.ietf.org/doc/html/rfc6749
