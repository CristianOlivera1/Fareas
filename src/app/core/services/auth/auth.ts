import { Injectable, computed, signal } from '@angular/core';
import { MockUser } from '../../models/user';

const STORAGE_KEY = 'fareas_mock_session';

const MOCK_USER: MockUser = {
  username: 'Admin Fareas',
  role: 'admin',
};

@Injectable({
  providedIn: 'root',
})
export class AuthService {
  private readonly session = signal<MockUser | null>(this.restore());

  readonly currentUser = this.session.asReadonly();
  readonly isAuthenticated = computed(() => this.session() !== null);
  readonly isAdmin = computed(() => this.session()?.role === 'admin');

  readonly userInitials = computed(() => {
    const user = this.session();
    if (!user?.username) return 'U';
    const parts = user.username.trim().split(/\s+/);
    if (parts.length >= 2) return `${parts[0][0]}${parts[1][0]}`.toUpperCase();
    return user.username.slice(0, 2).toUpperCase();
  });

  login(username: string): MockUser {
    const user: MockUser = { ...MOCK_USER, username: username.trim() || MOCK_USER.username };
    this.session.set(user);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(user));
    return user;
  }

  logout(): void {
    this.session.set(null);
    localStorage.removeItem(STORAGE_KEY);
  }

  private restore(): MockUser | null {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      return raw ? (JSON.parse(raw) as MockUser) : null;
    } catch {
      return null;
    }
  }
}
