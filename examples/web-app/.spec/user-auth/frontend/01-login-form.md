# Task: Login Form Component

**Status:** `pending`
**Depends:** #02-create-auth-endpoint (Wave 2 complete)
**Estimated:** 25 min
**Wave:** 3 — Frontend

## Objective

Build the login and registration form components for the frontend, along with auth context for managing authentication state.

## Acceptance Criteria

### Login Form
- [ ] Email input with validation
- [ ] Password input with show/hide toggle
- [ ] Submit button with loading state
- [ ] Error display for invalid credentials
- [ ] Link to registration page
- [ ] Redirects to dashboard on success

### Registration Form
- [ ] Email input with validation
- [ ] Password input with strength indicator
- [ ] Confirm password input
- [ ] Client-side validation matching backend rules
- [ ] Error display for duplicate email
- [ ] Redirects to login on success

### Auth Context
- [ ] Stores JWT token in localStorage
- [ ] Provides `useAuth()` hook with user state
- [ ] Automatic token refresh (Phase 2 — placeholder for now)
- [ ] Protected route wrapper component

## Implementation Notes

```typescript
// frontend/src/context/AuthContext.tsx
import React, { createContext, useContext, useState, useEffect } from 'react';

interface User {
  id: string;
  email: string;
  role: string;
}

interface AuthContextType {
  user: User | null;
  token: string | null;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  logout: () => void;
  loading: boolean;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(
    localStorage.getItem('auth_token')
  );
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (token) {
      fetchProfile(token).then(setUser).finally(() => setLoading(false));
    } else {
      setLoading(false);
    }
  }, [token]);

  const login = async (email: string, password: string) => {
    const response = await fetch('/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    });
    if (!response.ok) {
      throw new Error('Invalid credentials');
    }
    const { access_token } = await response.json();
    localStorage.setItem('auth_token', access_token);
    setToken(access_token);
  };

  const register = async (email: string, password: string) => {
    const response = await fetch('/auth/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    });
    if (!response.ok) {
      const data = await response.json();
      throw new Error(data.detail || 'Registration failed');
    }
  };

  const logout = () => {
    localStorage.removeItem('auth_token');
    setToken(null);
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ user, token, login, register, logout, loading }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used within AuthProvider');
  return context;
};
```

```tsx
// frontend/src/components/LoginForm.tsx
import React, { useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { useNavigate, Link } from 'react-router-dom';

export function LoginForm() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const { login } = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      await login(email, password);
      navigate('/dashboard');
    } catch (err) {
      setError('Invalid email or password');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-form">
      <h2>Sign In</h2>
      {error && <div className="error">{error}</div>}
      <form onSubmit={handleSubmit}>
        <input
          type="email"
          placeholder="Email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
        />
        <div className="password-field">
          <input
            type={showPassword ? 'text' : 'password'}
            placeholder="Password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
          <button
            type="button"
            onClick={() => setShowPassword(!showPassword)}
            className="toggle-password"
          >
            {showPassword ? '🙈' : '👁'}
          </button>
        </div>
        <button type="submit" disabled={loading}>
          {loading ? 'Signing in...' : 'Sign In'}
        </button>
      </form>
      <p>
        Don't have an account? <Link to="/register">Sign up</Link>
      </p>
    </div>
  );
}
```

### Component Structure

```
frontend/src/
├── components/
│   ├── LoginForm.tsx          # Login form
│   ├── RegisterForm.tsx       # Registration form
│   └── ProtectedRoute.tsx     # Auth route wrapper
├── context/
│   └── AuthContext.tsx         # Auth state management
└── hooks/
    └── useAuth.ts             # Re-export for convenience
```

### Validation Rules (Client-Side)

```typescript
export const validateEmail = (email: string): boolean => {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
};

export const validatePassword = (password: string): {
  valid: boolean;
  errors: string[];
} => {
  const errors: string[] = [];
  if (password.length < 8) errors.push('At least 8 characters');
  if (!/\d/.test(password)) errors.push('At least one number');
  return { valid: errors.length === 0, errors };
};
```

## Testing

```typescript
// LoginForm.test.tsx
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { AuthProvider } from '../context/AuthContext';
import { LoginForm } from './LoginForm';

describe('LoginForm', () => {
  it('renders email and password inputs', () => {
    render(<AuthProvider><LoginForm /></AuthProvider>);
    expect(screen.getByPlaceholderText('Email')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('Password')).toBeInTheDocument();
  });

  it('shows error on invalid credentials', async () => {
    // Mock fetch to return 401
    global.fetch = jest.fn().mockResolvedValueOnce({
      ok: false,
      status: 401,
      json: async () => ({ detail: 'Invalid credentials' }),
    });

    render(<AuthProvider><LoginForm /></AuthProvider>);
    fireEvent.change(screen.getByPlaceholderText('Email'), { target: { value: 'test@example.com' } });
    fireEvent.change(screen.getByPlaceholderText('Password'), { target: { value: 'wrong' } });
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }));

    await waitFor(() => {
      expect(screen.getByText('Invalid email or password')).toBeInTheDocument();
    });
  });
});
```

## References

- `skills/clean-code/SKILL.md` — Component design patterns
- React documentation: Forms and Controlled Components
