import { goto } from '$app/navigation';

export type UserRole = 'super_admin' | 'admin' | 'user';

export type User = {
  uuid: string;
  name: string;
  email: string | null;
  phone_e164: string | null;
  role: UserRole;
  last_login_at?: string | null;
};

class AuthState {
  user = $state<User | null>(null);
  loading = $state(true);

  async refresh() {
    try {
      const r = await fetch('/api/auth/me', { credentials: 'include' });
      if (r.ok) {
        this.user = (await r.json()) as User;
      } else {
        this.user = null;
      }
    } catch {
      this.user = null;
    } finally {
      this.loading = false;
    }
  }

  async login(identifier: string, secret: string): Promise<User> {
    const r = await fetch('/api/auth/login', {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ identifier, secret })
    });
    if (!r.ok) {
      const err = await r.json().catch(() => ({}));
      throw new Error(err.detail || 'Login failed');
    }
    this.user = (await r.json()) as User;
    return this.user;
  }

  async logout() {
    try {
      await fetch('/api/auth/logout', {
        method: 'POST',
        credentials: 'include'
      });
    } catch {
      // ignore network errors on logout
    }
    this.user = null;
    goto('/login');
  }

  get isAdmin(): boolean {
    return this.user?.role === 'admin' || this.user?.role === 'super_admin';
  }

  get isSuperAdmin(): boolean {
    return this.user?.role === 'super_admin';
  }
}

export const auth = new AuthState();
