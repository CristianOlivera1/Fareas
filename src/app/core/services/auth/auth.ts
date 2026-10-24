import { Injectable, computed, inject, signal } from '@angular/core';
import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Router } from '@angular/router';
import {
  Observable,
  TimeoutError,
  catchError,
  defer,
  finalize,
  from,
  lastValueFrom,
  map,
  of,
  shareReplay,
  tap,
  throwError,
  timeout,
} from 'rxjs';
import { environment } from '../../../../environments/environment';
import type {
  ChangePasswordOtpRequest,
  ChangePasswordOtpResponse,
  ChangePasswordRequest,
  ChangePasswordResponse,
  LoginRequest,
  LoginResponse,
  MessageResponse,
  RecoverRequest,
  RecoverResponse,
  RefreshTokenRequest,
  ResetPasswordRequest,
  SessionUser,
  TokenPairResponse,
  UserOut,
  VerifyChangePasswordOtpRequest,
  VerifyOtpRequest,
} from '../../models/user';
import type { RateLimitState } from '../../models/rate-limit-state';
import { LOCKOUT_MS, RATE_LIMIT_MAX, RATE_LIMIT_WINDOW_MS } from '../../constants/auth-rate-limit';
import {
  ACCESS_TOKEN_EXPIRES_AT_KEY,
  ACCESS_TOKEN_KEY,
  REFRESH_TOKEN_EXPIRES_AT_KEY,
  REFRESH_TOKEN_KEY,
  SESSION_KEY,
} from '../../constants/auth-storage';

export class SessionChangedError extends HttpErrorResponse {
  constructor() {
    super({
      status: 409,
      statusText: 'Conflict',
      error: { detail: 'La sesión cambió durante la renovación' },
    });
  }
}

@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly http = inject(HttpClient);
  private readonly router = inject(Router);
  private readonly api = environment.apiUrl;

  private readonly session = signal<SessionUser | null>(this.restoreSession());
  private readonly token = signal<string | null>(this.readStorage(ACCESS_TOKEN_KEY));
  private readonly refreshToken = signal<string | null>(this.readStorage(REFRESH_TOKEN_KEY));
  private readonly accessTokenExpiresAt = signal<number | null>(
    this.readTimestamp(ACCESS_TOKEN_EXPIRES_AT_KEY),
  );
  private readonly refreshTokenExpiresAt = signal<number | null>(
    this.readTimestamp(REFRESH_TOKEN_EXPIRES_AT_KEY),
  );

  private refreshRequest$: Observable<TokenPairResponse> | null = null;
  private refreshRequestKey: object | null = null;
  private authEpoch = 0;
  private sessionExpiredHandled = false;

  readonly currentUser = this.session.asReadonly();
  readonly accessToken = this.token.asReadonly();
  readonly isAuthenticated = computed(
    () => this.session() !== null && (this.token() !== null || this.refreshToken() !== null),
  );
  readonly isAdmin = computed(() => this.session()?.role === 'admin');
  readonly isDocente = computed(() => this.session()?.role === 'docente');
  readonly isEstudiante = computed(() => this.session()?.role === 'estudiante');
  readonly mustChangePassword = computed(() => this.session()?.must_change_password ?? false);

  readonly avatarUrl = computed(() => this.session()?.avatar_url ?? null);

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

  /**
   * Restores a persisted session before the router performs its first navigation.
   * A valid access token is reused; an expired or missing access token is renewed
   * with the refresh token. Network failures leave the session intact so the user
   * can retry once connectivity returns.
   */
  initialize(): Observable<void> {
    const session = this.session();
    const accessToken = this.token();
    const refreshToken = this.refreshToken();

    if (!session || (!accessToken && !refreshToken)) {
      if (session || accessToken || refreshToken) this.clearAuth();
      return of(void 0);
    }

    if (refreshToken && this.isRefreshTokenExpired()) {
      this.clearAuth();
      return of(void 0);
    }

    if (accessToken && !this.isAccessTokenExpired()) {
      return of(void 0);
    }

    if (!refreshToken) {
      if (accessToken && this.isAccessTokenExpired()) this.clearAuth();
      return of(void 0);
    }

    return this.refreshTokens().pipe(
      map(() => void 0),
      timeout(10_000),
      catchError((error: unknown) => {
        if (error instanceof TimeoutError) this.clearAuth();
        return of(void 0);
      }),
    );
  }

  login(request: LoginRequest): Observable<LoginResponse> {
    const lockCheck = this.checkRateLimit();
    if (lockCheck) {
      return throwError(
        () =>
          new HttpErrorResponse({
            status: 429,
            statusText: 'Too Many Requests',
            error: { detail: lockCheck },
          }),
      );
    }

    return this.http.post<LoginResponse>(`${this.api}/auth/login`, request).pipe(
      tap((res) => {
        this.resetRateLimit();
        this.persistAuth(res);
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
        this.writeStorage(SESSION_KEY, JSON.stringify(sessionUser));
      }),
    );
  }

  uploadAvatar(file: File): Observable<{ avatar_url: string | null }> {
    const body = new FormData();
    body.append('file', file);
    return this.http
      .put<{ avatar_url: string | null }>(`${this.api}/auth/me/avatar`, body)
      .pipe(tap((result) => this.patchSession({ avatar_url: result.avatar_url })));
  }

  removeAvatar(): Observable<void> {
    return this.http
      .delete<void>(`${this.api}/auth/me/avatar`)
      .pipe(tap(() => this.patchSession({ avatar_url: null })));
  }

  validateToken(): Observable<boolean> {
    if (!this.isAuthenticated()) return of(false);
    return this.me().pipe(
      map(() => true),
      catchError(() => {
        this.clearAuth();
        return of(false);
      }),
    );
  }

  requestChangePasswordOtp(
    request: ChangePasswordOtpRequest,
  ): Observable<ChangePasswordOtpResponse> {
    return this.http.post<ChangePasswordOtpResponse>(
      `${this.api}/auth/change-password/otp`,
      request,
    );
  }

  verifyChangePasswordOtp(request: VerifyChangePasswordOtpRequest): Observable<MessageResponse> {
    return this.http.post<MessageResponse>(`${this.api}/auth/change-password/otp/verify`, request);
  }

  changePassword(request: ChangePasswordRequest): Observable<ChangePasswordResponse> {
    return this.http
      .post<ChangePasswordResponse>(`${this.api}/auth/change-password`, request)
      .pipe(tap((response) => this.applyPasswordChange(response)));
  }

  recoverRequest(request: RecoverRequest): Observable<RecoverResponse> {
    return this.http.post<RecoverResponse>(`${this.api}/auth/recover`, request);
  }

  verifyOtp(request: VerifyOtpRequest): Observable<MessageResponse> {
    return this.http.post<MessageResponse>(`${this.api}/auth/recover/verify`, request);
  }

  resetPassword(request: ResetPasswordRequest): Observable<MessageResponse> {
    return this.http.post<MessageResponse>(`${this.api}/auth/recover/reset`, request);
  }

  /**
   * Single-flight refresh. The backend rotates and invalidates the previous token,
   * so concurrent 401s must share one request. A Web Lock serializes refreshes
   * across tabs when the browser supports it.
   */
  refreshTokens(): Observable<TokenPairResponse> {
    if (this.refreshRequest$) return this.refreshRequest$;

    const epoch = this.authEpoch;
    const requestKey = {};
    const source$ = this.withRefreshLock(() => {
      if (epoch !== this.authEpoch) {
        return throwError(() => new SessionChangedError());
      }

      const refreshToken = this.readStorage(REFRESH_TOKEN_KEY) ?? this.refreshToken();
      if (!refreshToken) {
        this.clearAuth();
        return throwError(() => this.sessionExpiredError());
      }

      const body: RefreshTokenRequest = { refresh_token: refreshToken };
      return this.http.post<TokenPairResponse>(`${this.api}/auth/refresh`, body).pipe(
        tap((tokens) => {
          if (epoch === this.authEpoch) this.persistTokens(tokens);
        }),
        catchError((error: HttpErrorResponse) => {
          if (epoch === this.authEpoch && this.isSessionInvalid(error.status)) {
            this.clearAuth();
          }
          return throwError(() => error);
        }),
      );
    }).pipe(
      finalize(() => {
        if (this.refreshRequestKey === requestKey) {
          this.refreshRequest$ = null;
          this.refreshRequestKey = null;
        }
      }),
    );

    const shared$ = source$.pipe(shareReplay({ bufferSize: 1, refCount: false }));
    this.refreshRequestKey = requestKey;
    this.refreshRequest$ = shared$;
    return shared$;
  }

  logout(): void {
    const refreshToken = this.readStorage(REFRESH_TOKEN_KEY) ?? this.refreshToken();
    this.clearAuth();
    this.sessionExpiredHandled = false;

    if (refreshToken) {
      const body: RefreshTokenRequest = { refresh_token: refreshToken };
      this.http.post<void>(`${this.api}/auth/logout`, body).subscribe({ error: () => undefined });
    }

    void this.router.navigate(['/login']).catch(() => false);
  }

  handleSessionExpired(): void {
    this.clearAuth();
    if (this.sessionExpiredHandled) return;

    this.sessionExpiredHandled = true;
    void this.router
      .navigate(['/login'], { queryParams: { reason: 'session_expired' } })
      .catch(() => false);
  }

  clearAuth(): void {
    this.authEpoch++;
    this.invalidateRefreshRequest();
    this.token.set(null);
    this.refreshToken.set(null);
    this.accessTokenExpiresAt.set(null);
    this.refreshTokenExpiresAt.set(null);
    this.session.set(null);
    this.writeStorage(ACCESS_TOKEN_KEY, null);
    this.writeStorage(REFRESH_TOKEN_KEY, null);
    this.writeStorage(ACCESS_TOKEN_EXPIRES_AT_KEY, null);
    this.writeStorage(REFRESH_TOKEN_EXPIRES_AT_KEY, null);
    this.writeStorage(SESSION_KEY, null);
  }

  private persistAuth(response: LoginResponse): void {
    this.authEpoch++;
    this.invalidateRefreshRequest();
    this.persistTokens(response);
    const sessionUser = this.mapToSession(response.user);
    this.session.set(sessionUser);
    this.writeStorage(SESSION_KEY, JSON.stringify(sessionUser));
    this.sessionExpiredHandled = false;
  }

  private applyPasswordChange(response: ChangePasswordResponse): void {
    this.authEpoch++;
    this.invalidateRefreshRequest();

    if (response.access_token) {
      if (
        response.refresh_token &&
        response.expires_in !== undefined &&
        response.refresh_expires_in !== undefined
      ) {
        this.persistTokens({
          access_token: response.access_token,
          refresh_token: response.refresh_token,
          token_type: response.token_type ?? 'bearer',
          expires_in: response.expires_in,
          refresh_expires_in: response.refresh_expires_in,
        });
      } else {
        this.setAccessToken(response.access_token, response.expires_in);
        this.clearRefreshToken();
      }
    }

    const current = this.session();
    if (current) {
      const updated = { ...current, must_change_password: false };
      this.session.set(updated);
      this.writeStorage(SESSION_KEY, JSON.stringify(updated));
    }
  }

  private patchSession(changes: Partial<SessionUser>): void {
    const current = this.session();
    if (!current) return;
    const updated = { ...current, ...changes };
    this.session.set(updated);
    this.writeStorage(SESSION_KEY, JSON.stringify(updated));
  }

  private persistTokens(tokens: TokenPairResponse): void {
    const now = Date.now();
    const accessSeconds = Number.isFinite(tokens.expires_in) ? tokens.expires_in : 0;
    const refreshSeconds = Number.isFinite(tokens.refresh_expires_in)
      ? tokens.refresh_expires_in
      : 0;
    const accessExpiresAt = now + Math.max(0, accessSeconds) * 1000;
    const refreshExpiresAt = now + Math.max(0, refreshSeconds) * 1000;

    this.token.set(tokens.access_token);
    this.refreshToken.set(tokens.refresh_token);
    this.accessTokenExpiresAt.set(accessExpiresAt);
    this.refreshTokenExpiresAt.set(refreshExpiresAt);

    this.writeStorage(ACCESS_TOKEN_KEY, tokens.access_token);
    this.writeStorage(REFRESH_TOKEN_KEY, tokens.refresh_token);
    this.writeStorage(ACCESS_TOKEN_EXPIRES_AT_KEY, String(accessExpiresAt));
    this.writeStorage(REFRESH_TOKEN_EXPIRES_AT_KEY, String(refreshExpiresAt));
  }

  private setAccessToken(token: string, expiresIn?: number): void {
    this.token.set(token);
    this.writeStorage(ACCESS_TOKEN_KEY, token);

    if (expiresIn !== undefined && Number.isFinite(expiresIn)) {
      const expiresAt = Date.now() + Math.max(0, expiresIn) * 1000;
      this.accessTokenExpiresAt.set(expiresAt);
      this.writeStorage(ACCESS_TOKEN_EXPIRES_AT_KEY, String(expiresAt));
    } else {
      this.accessTokenExpiresAt.set(null);
      this.writeStorage(ACCESS_TOKEN_EXPIRES_AT_KEY, null);
    }
  }

  private clearRefreshToken(): void {
    this.refreshToken.set(null);
    this.refreshTokenExpiresAt.set(null);
    this.writeStorage(REFRESH_TOKEN_KEY, null);
    this.writeStorage(REFRESH_TOKEN_EXPIRES_AT_KEY, null);
  }

  private invalidateRefreshRequest(): void {
    this.refreshRequest$ = null;
    this.refreshRequestKey = null;
  }

  private withRefreshLock<T>(operation: () => Observable<T>): Observable<T> {
    const locks = typeof navigator !== 'undefined' ? navigator.locks : undefined;
    if (!locks) return defer(operation);

    return defer(() =>
      from(locks.request('fareas-refresh-token', () => lastValueFrom(operation())) as Promise<T>),
    );
  }

  private isAccessTokenExpired(): boolean {
    const expiresAt = this.accessTokenExpiresAt();
    return expiresAt !== null && Date.now() >= expiresAt;
  }

  private isRefreshTokenExpired(): boolean {
    const expiresAt = this.refreshTokenExpiresAt();
    return expiresAt !== null && Date.now() >= expiresAt;
  }

  private isSessionInvalid(status: number): boolean {
    return status === 400 || status === 401 || status === 403 || status === 422;
  }

  private sessionExpiredError(): HttpErrorResponse {
    return new HttpErrorResponse({
      status: 401,
      statusText: 'Unauthorized',
      error: { detail: 'Sesión expirada' },
    });
  }

  private readStorage(key: string): string | null {
    try {
      return localStorage.getItem(key);
    } catch {
      return null;
    }
  }

  private writeStorage(key: string, value: string | null): void {
    try {
      if (value === null) {
        localStorage.removeItem(key);
      } else {
        localStorage.setItem(key, value);
      }
    } catch {
      // Storage can be unavailable (private mode, quota). In-memory state still works.
    }
  }

  private readTimestamp(key: string): number | null {
    const raw = this.readStorage(key);
    if (!raw) return null;
    const value = Number(raw);
    return Number.isFinite(value) ? value : null;
  }

  private restoreSession(): SessionUser | null {
    try {
      const raw = this.readStorage(SESSION_KEY);
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
      avatar_url: user.avatar_url ?? null,
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
