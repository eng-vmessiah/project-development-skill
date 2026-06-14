# Specification: User Authentication

**Feature:** User Authentication System
**Project:** TaskFlow — Task Management Application
**Author:** Development Team
**Created:** 2026-06-14

## Overview

Implement a complete user authentication system for TaskFlow, enabling users to register, log in, and manage their profiles. The system uses JWT tokens for stateless authentication with bcrypt password hashing.

## Requirements

### Functional
1. User registration with email and password
2. User login returning a JWT access token
3. Protected endpoint to retrieve current user profile
4. Password validation (minimum 8 characters, at least one number)
5. Duplicate email prevention
6. Secure password storage (bcrypt, never plaintext)

### Non-Functional
1. Response time < 200ms for auth endpoints
2. Tokens expire after 24 hours
3. Rate limiting: max 10 registration attempts per IP per hour
4. All endpoints return proper HTTP status codes
5. API documentation via OpenAPI/Swagger

## Endpoints

| Method | Path | Auth Required | Description |
|--------|------|---------------|-------------|
| POST | `/auth/register` | No | Create new user account |
| POST | `/auth/login` | No | Authenticate and get token |
| GET | `/auth/me` | Yes | Get current user profile |
| PUT | `/auth/me` | Yes | Update current user profile |

## Data Models

### User
```
id: string (UUID)
email: string (unique, indexed)
hashed_password: string (bcrypt)
created_at: datetime (auto)
updated_at: datetime (auto, nullable)
```

### TokenResponse
```
access_token: string
token_type: string ("bearer")
expires_in: integer (seconds)
```

## Security Considerations
- Passwords hashed with bcrypt (cost factor 12)
- No password in any response payload
- JWT contains only user ID (no sensitive data)
- Tokens transmitted via Authorization header (Bearer scheme)
- Rate limiting on registration and login endpoints

## Out of Scope
- Email verification (Phase 2)
- Password reset flow (Phase 2)
- OAuth/social login (Phase 3)
- Multi-factor authentication (Phase 3)
- Session management/refresh tokens (Phase 2)
