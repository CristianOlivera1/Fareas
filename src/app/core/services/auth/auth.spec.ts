import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';
import { vi } from 'vitest';

import {
  ACCESS_TOKEN_EXPIRES_AT_KEY,
  ACCESS_TOKEN_KEY,
  REFRESH_TOKEN_EXPIRES_AT_KEY,
  REFRESH_TOKEN_KEY,
  SESSION_KEY,
} from '../../constants/auth-storage';
import { AuthService } from './auth';

const API = 'http://localhost:8000/api/v1';
const USER = {
  id: 1,
  role: 'admin' as const,
  full_name: 'Admin Fareas',
  email: 'admin@unamba.edu.pe',
  must_change_password: false,
};
const LOGIN_RESPONSE = {
  access_token: 'access-1',
  refresh_token: 'refresh-1',
  token_type: 'bearer',
  expires_in: 7200,
  refresh_expires_in: 2_592_000,
  user: USER,
};
const REFRESH_RESPONSE = {
  access_token: 'access-2',
  refresh_token: 'refresh-2',
  token_type: 'bearer',
  expires_in: 7200,
  refresh_expires_in: 2_592_000,
};

describe('AuthService', () => {
  let service: AuthService;
  let httpMock: HttpTestingController;

  beforeEach(() => {
    localStorage.clear();
    TestBed.configureTestingModule({
      providers: [provideRouter([]), provideHttpClient(), provideHttpClientTesting()],
    });
    service = TestBed.inject(AuthService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpMock.verify();
    localStorage.clear();
  });

  function login(): void {
    service.login({ email: USER.email, password: 'Clave1234' }).subscribe();
    httpMock.expectOne(`${API}/auth/login`).flush(LOGIN_RESPONSE);
  }

  function storeSession(accessExpiresAt: number, refreshExpiresAt: number): void {
    localStorage.setItem(ACCESS_TOKEN_KEY, 'access-old');
    localStorage.setItem(REFRESH_TOKEN_KEY, 'refresh-old');
    localStorage.setItem(ACCESS_TOKEN_EXPIRES_AT_KEY, String(accessExpiresAt));
    localStorage.setItem(REFRESH_TOKEN_EXPIRES_AT_KEY, String(refreshExpiresAt));
    localStorage.setItem(SESSION_KEY, JSON.stringify(USER));
  }

  it('persists both tokens and the session on login', () => {
    login();

    expect(service.isAuthenticated()).toBe(true);
    expect(service.accessToken()).toBe('access-1');
    expect(service.currentUser()?.id).toBe(USER.id);
    expect(localStorage.getItem(ACCESS_TOKEN_KEY)).toBe('access-1');
    expect(localStorage.getItem(REFRESH_TOKEN_KEY)).toBe('refresh-1');
    expect(localStorage.getItem(SESSION_KEY)).toContain('Admin Fareas');
  });

  it('revokes the refresh token on logout and clears local state', () => {
    login();
    const router = TestBed.inject(Router);
    const navigate = vi.spyOn(router, 'navigate').mockResolvedValue(true);

    service.logout();

    const req = httpMock.expectOne(`${API}/auth/logout`);
    expect(req.request.body).toEqual({ refresh_token: 'refresh-1' });
    req.flush(null, { status: 204, statusText: 'No Content' });

    expect(service.isAuthenticated()).toBe(false);
    expect(localStorage.getItem(REFRESH_TOKEN_KEY)).toBeNull();
    expect(navigate).toHaveBeenCalledWith(['/login']);
  });

  it('persists the rotated pair after a password change', () => {
    login();

    service
      .changePassword({ current_password: 'Clave1234', new_password: 'NuevaClave99' })
      .subscribe();
    const req = httpMock.expectOne(`${API}/auth/change-password`);
    req.flush({
      message: 'Contraseña actualizada',
      access_token: 'access-3',
      refresh_token: 'refresh-3',
      token_type: 'bearer',
      expires_in: 7200,
      refresh_expires_in: 60,
    });

    expect(service.accessToken()).toBe('access-3');
    expect(localStorage.getItem(REFRESH_TOKEN_KEY)).toBe('refresh-3');
    expect(service.mustChangePassword()).toBe(false);
  });

  it('does not refresh a session that changed before the request started', () => {
    login();
    const router = TestBed.inject(Router);
    vi.spyOn(router, 'navigate').mockResolvedValue(true);

    const staleRefresh = service.refreshTokens();
    service.logout();
    httpMock.expectOne(`${API}/auth/logout`).flush(null, {
      status: 204,
      statusText: 'No Content',
    });

    let errorStatus = 0;
    staleRefresh.subscribe({ error: (error) => (errorStatus = error.status) });

    expect(errorStatus).toBe(409);
    httpMock.expectNone(`${API}/auth/refresh`);
  });

  it('shares one refresh request between concurrent callers', () => {
    login();

    let firstAccess = '';
    let secondAccess = '';
    service.refreshTokens().subscribe((tokens) => (firstAccess = tokens.access_token));
    service.refreshTokens().subscribe((tokens) => (secondAccess = tokens.access_token));

    const req = httpMock.expectOne(`${API}/auth/refresh`);
    expect(req.request.body).toEqual({ refresh_token: 'refresh-1' });
    req.flush(REFRESH_RESPONSE);

    expect(firstAccess).toBe('access-2');
    expect(secondAccess).toBe('access-2');
    expect(service.accessToken()).toBe('access-2');
    expect(localStorage.getItem(REFRESH_TOKEN_KEY)).toBe('refresh-2');
  });

  it('clears the session when the refresh token is rejected', () => {
    login();

    let errorStatus = 0;
    service.refreshTokens().subscribe({ error: (error) => (errorStatus = error.status) });
    httpMock
      .expectOne(`${API}/auth/refresh`)
      .flush({ detail: 'reutilizado' }, { status: 401, statusText: 'Unauthorized' });

    expect(errorStatus).toBe(401);
    expect(service.isAuthenticated()).toBe(false);
    expect(localStorage.getItem(REFRESH_TOKEN_KEY)).toBeNull();
    expect(localStorage.getItem(SESSION_KEY)).toBeNull();
  });

  it('keeps the session on a transient refresh failure', () => {
    login();

    let errorStatus = -1;
    service.refreshTokens().subscribe({ error: (error) => (errorStatus = error.status) });
    httpMock.expectOne(`${API}/auth/refresh`).error(new ProgressEvent('error'));

    expect(errorStatus).toBe(0);
    expect(service.isAuthenticated()).toBe(true);
    expect(localStorage.getItem(REFRESH_TOKEN_KEY)).toBe('refresh-1');
  });

  it('refreshes an expired access token during startup', () => {
    storeSession(Date.now() - 1_000, Date.now() + 60_000);
    const restored = TestBed.runInInjectionContext(() => new AuthService());

    let completed = false;
    restored.initialize().subscribe(() => (completed = true));

    httpMock.expectOne(`${API}/auth/refresh`).flush(REFRESH_RESPONSE);

    expect(completed).toBe(true);
    expect(restored.isAuthenticated()).toBe(true);
    expect(restored.accessToken()).toBe('access-2');
  });

  it('does not refresh when the stored access token is still valid', () => {
    storeSession(Date.now() + 60_000, Date.now() + 120_000);
    const restored = TestBed.runInInjectionContext(() => new AuthService());

    let completed = false;
    restored.initialize().subscribe(() => (completed = true));

    httpMock.expectNone(`${API}/auth/refresh`);
    expect(completed).toBe(true);
    expect(restored.accessToken()).toBe('access-old');
  });

  it('clears a legacy session without a refresh token once access expires', () => {
    localStorage.setItem(ACCESS_TOKEN_KEY, 'access-old');
    localStorage.setItem(ACCESS_TOKEN_EXPIRES_AT_KEY, String(Date.now() - 1_000));
    localStorage.setItem(SESSION_KEY, JSON.stringify(USER));
    const restored = TestBed.runInInjectionContext(() => new AuthService());

    restored.initialize().subscribe();

    httpMock.expectNone(`${API}/auth/refresh`);
    expect(restored.isAuthenticated()).toBe(false);
    expect(localStorage.getItem(SESSION_KEY)).toBeNull();
  });
});
