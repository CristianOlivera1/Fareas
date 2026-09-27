import { Injectable, computed, inject, signal } from '@angular/core';
import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Router } from '@angular/router';
import { Observable, catchError, map, of, tap, throwError } from 'rxjs';
import { environment } from '../../../../environments/environment';
import type {
  ChangePasswordRequest,
  LoginRequest,
  LoginResponse,
  MessageResponse,
  RecoverRequest,
  ResetPasswordRequest,
  SessionUser,
  UserOut,
  VerifyOtpRequest,
} from '../../models/user';
import type { RateLimitState } from '../../models/rate-limit-state';
import { LOCKOUT_MS, RATE_LIMIT_MAX, RATE_LIMIT_WINDOW_MS } from '../../constants/auth-rate-limit';
import { ACCESS_TOKEN_KEY, SESSION_KEY } from '../../constants/auth-storage';

@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly http = inject(HttpClient);
  private readonly router = inject(Router);
  private readonly api = environment.apiUrl;

  private readonly session = signal<SessionUser | null>(this.restoreSession());
  private readonly token = signal<string | null>(this.restoreToken(ACCESS_TOKEN_KEY));

  readonly currentUser = this.session.asReadonly();
  readonly accessToken = this.token.asReadonly();
  readonly isAuthenticated = computed(() => this.session() !== null && this.token() !== null);
  readonly isAdmin = computed(() => this.session()?.role === 'admin');
  readonly isDocente = computed(() => this.session()?.role === 'docente');
  readonly isEstudiante = computed(() => this.session()?.role === 'estudiante');
  readonly mustChangePassword = computed(() => this.session()?.must_change_password ?? false);

  readonly userInitials = computed(() => {
    const user = this.session();
    if (!user?.full_name) return 'U';
    const parts = user.full_name.trim().split(/\s+/);
    if (parts.length >= 2) return `${parts[0][0]}${parts[1][0]}`.toUpperCase();
    return user.full_name.slice(0, 2).toUpperCase();
  });

  private readonly rateLimitState: RateLimitState = {
    attempts: 0,
    windowStart: Date.now(),
    lockedUntil: 0,
  };

  login(request: LoginRequest): Observable<LoginResponse> {
    const lockCheck = this.checkRateLimit();
    if (lockCheck) {
      return throwError(() => new HttpErrorResponse({
        status: 429,
        statusText: 'Too Many Requests',
        error: { detail: lockCheck },
      }));
    }

    return this.http.post<LoginResponse>(`${this.api}/auth/login`, request).pipe(
      tap((res) => {
        this.resetRateLimit();
        this.persistAuth(res.access_token, res.user);
      }),
      catchError((err: HttpErrorResponse) => {
        this.recordFailedAttempt();
        return throwError(() => err);
      }),
    );
  }

  me(): Observable<UserOut> {
    return this.http.get<UserOut>(`${this.api}/auth/me`).pipe(
      tap((user) => {
        const sessionUser = this.mapToSession(user);
        this.session.set(sessionUser);
        localStorage.setItem(SESSION_KEY, JSON.stringify(sessionUser));
      }),
    );
  }

  validateToken(): Observable<boolean> {
    if (!this.token()) return of(false);
    return this.me().pipe(
      map(() => true),
      catchError(() => {
        this.clearAuth();
        return of(false);
      }),
    );
  }

  changePassword(request: ChangePasswordRequest): Observable<MessageResponse> {
    return this.http.post<MessageResponse>(`${this.api}/auth/change-password`, request).pipe(
      tap(() => {
        const current = this.session();
        if (current) {
          const updated = { ...current, must_change_password: false };
          this.session.set(updated);
          localStorage.setItem(SESSION_KEY, JSON.stringify(updated));
        }
      }),
    );
  }

  recoverRequest(request: RecoverRequest): Observable<MessageResponse> {
    return this.http.post<MessageResponse>(`${this.api}/auth/recover`, request);
  }

  verifyOtp(request: VerifyOtpRequest): Observable<MessageResponse> {
    return this.http.post<MessageResponse>(`${this.api}/auth/recover/verify`, request);
  }

  resetPassword(request: ResetPasswordRequest): Observable<MessageResponse> {
    return this.http.post<MessageResponse>(`${this.api}/auth/recover/reset`, request);
  }

  logout(): void {
    // Sin refresh tokens: el logout es cliente (descartar el token).
    this.clearAuth();
    void this.router.navigate(['/login']);
  }

  private persistAuth(accessToken: string, user: UserOut): void {
    const sessionUser = this.mapToSession(user);
    this.token.set(accessToken);
    this.session.set(sessionUser);
    localStorage.setItem(ACCESS_TOKEN_KEY, accessToken);
    localStorage.setItem(SESSION_KEY, JSON.stringify(sessionUser));
  }

  clearAuth(): void {
    this.token.set(null);
    this.session.set(null);
    localStorage.removeItem(ACCESS_TOKEN_KEY);
    localStorage.removeItem(SESSION_KEY);
  }

  private restoreToken(key: string): string | null {
    try {
      return localStorage.getItem(key);
    } catch {
      return null;
    }
  }

  private restoreSession(): SessionUser | null {
    try {
      const raw = localStorage.getItem(SESSION_KEY);
      if (!raw) return null;
      const parsed = JSON.parse(raw) as SessionUser;
      if (!parsed?.id || !parsed?.role || !parsed?.full_name) return null;
      return parsed;
    } catch {
      return null;
    }
  }

  private mapToSession(user: UserOut): SessionUser {
    return {
      id: user.id,
      full_name: user.full_name,
      email: user.email,
      role: user.role,
      must_change_password: user.must_change_password,
    };
  }

  private checkRateLimit(): string | null {
    const now = Date.now();
    if (now < this.rateLimitState.lockedUntil) {
      const secsLeft = Math.ceil((this.rateLimitState.lockedUntil - now) / 1000);
      return `Demasiados intentos. Espera ${secsLeft} segundos.`;
    }
    if (now - this.rateLimitState.windowStart > RATE_LIMIT_WINDOW_MS) {
      this.resetRateLimit();
    }
    return null;
  }

  private recordFailedAttempt(): void {
    const now = Date.now();
    if (now - this.rateLimitState.windowStart > RATE_LIMIT_WINDOW_MS) {
      this.rateLimitState.attempts = 1;
      this.rateLimitState.windowStart = now;
    } else {
      this.rateLimitState.attempts++;
    }
    if (this.rateLimitState.attempts >= RATE_LIMIT_MAX) {
      this.rateLimitState.lockedUntil = now + LOCKOUT_MS;
    }
  }

  private resetRateLimit(): void {
    this.rateLimitState.attempts = 0;
    this.rateLimitState.windowStart = Date.now();
    this.rateLimitState.lockedUntil = 0;
  }
}
