import { HttpClient, provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';
import { vi } from 'vitest';

import { AuthService } from '../services/auth/auth';
import { authInterceptor } from './auth';

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

describe('authInterceptor', () => {
  let http: HttpClient;
  let httpMock: HttpTestingController;
  let auth: AuthService;
  let router: Router;

  beforeEach(() => {
    localStorage.clear();
    TestBed.configureTestingModule({
      providers: [
        provideRouter([]),
        provideHttpClient(withInterceptors([authInterceptor])),
        provideHttpClientTesting(),
      ],
    });
    http = TestBed.inject(HttpClient);
    httpMock = TestBed.inject(HttpTestingController);
    auth = TestBed.inject(AuthService);
    router = TestBed.inject(Router);
  });

  afterEach(() => {
    httpMock.verify();
    localStorage.clear();
  });

  function login(): void {
    auth.login({ email: USER.email, password: 'Clave1234' }).subscribe();
    const req = httpMock.expectOne(`${API}/auth/login`);
    expect(req.request.headers.has('Authorization')).toBe(false);
    req.flush(LOGIN_RESPONSE);
  }

  it('does not attach tokens or refresh requests outside the API', () => {
    login();

    let errorStatus = 0;
    http.get('https://example.com/data').subscribe({
      error: (error) => (errorStatus = error.status),
    });

    const req = httpMock.expectOne('https://example.com/data');
    expect(req.request.headers.has('Authorization')).toBe(false);
    req.flush({ detail: 'no autorizado' }, { status: 401, statusText: 'Unauthorized' });

    expect(errorStatus).toBe(401);
    expect(auth.isAuthenticated()).toBe(true);
    httpMock.expectNone(`${API}/auth/refresh`);
  });

  it('attaches the access token and refreshes once on 401', () => {
    login();

    let data: unknown;
    http.get(`${API}/courses`).subscribe((value) => (data = value));

    const first = httpMock.expectOne(`${API}/courses`);
    expect(first.request.headers.get('Authorization')).toBe('Bearer access-1');
    first.flush({ detail: 'expirado' }, { status: 401, statusText: 'Unauthorized' });

    const refresh = httpMock.expectOne(`${API}/auth/refresh`);
    expect(refresh.request.headers.has('Authorization')).toBe(false);
    expect(refresh.request.body).toEqual({ refresh_token: 'refresh-1' });
    refresh.flush(REFRESH_RESPONSE);

    const retry = httpMock.expectOne(`${API}/courses`);
    expect(retry.request.headers.get('Authorization')).toBe('Bearer access-2');
    retry.flush({ id: 1 });

    expect(data).toEqual({ id: 1 });
    expect(auth.accessToken()).toBe('access-2');
  });

  it('uses a single refresh request for concurrent 401 responses', () => {
    login();

    let coursesData: unknown;
    let studentsData: unknown;
    http.get(`${API}/courses`).subscribe((value) => (coursesData = value));
    http.get(`${API}/students`).subscribe((value) => (studentsData = value));

    httpMock
      .expectOne(`${API}/courses`)
      .flush({ detail: 'expirado' }, { status: 401, statusText: 'Unauthorized' });
    httpMock
      .expectOne(`${API}/students`)
      .flush({ detail: 'expirado' }, { status: 401, statusText: 'Unauthorized' });

    const refresh = httpMock.expectOne(`${API}/auth/refresh`);
    refresh.flush(REFRESH_RESPONSE);

    httpMock.expectOne(`${API}/courses`).flush({ ok: 'courses' });
    httpMock.expectOne(`${API}/students`).flush({ ok: 'students' });

    expect(coursesData).toEqual({ ok: 'courses' });
    expect(studentsData).toEqual({ ok: 'students' });
  });

  it('clears the session and redirects when refresh is rejected', () => {
    login();
    const navigate = vi.spyOn(router, 'navigate').mockResolvedValue(true);

    let errorStatus = 0;
    http.get(`${API}/courses`).subscribe({ error: (error) => (errorStatus = error.status) });

    httpMock
      .expectOne(`${API}/courses`)
      .flush({ detail: 'expirado' }, { status: 401, statusText: 'Unauthorized' });
    httpMock
      .expectOne(`${API}/auth/refresh`)
      .flush({ detail: 'reutilizado' }, { status: 401, statusText: 'Unauthorized' });

    expect(errorStatus).toBe(401);
    expect(auth.isAuthenticated()).toBe(false);
    expect(navigate).toHaveBeenCalledWith(['/login'], {
      queryParams: { reason: 'session_expired' },
    });
  });

  it('does not refresh more than once when the retried request also returns 401', () => {
    login();
    const navigate = vi.spyOn(router, 'navigate').mockResolvedValue(true);

    let errorStatus = 0;
    http.get(`${API}/courses`).subscribe({ error: (error) => (errorStatus = error.status) });

    httpMock
      .expectOne(`${API}/courses`)
      .flush({ detail: 'expirado' }, { status: 401, statusText: 'Unauthorized' });
    httpMock.expectOne(`${API}/auth/refresh`).flush(REFRESH_RESPONSE);
    httpMock
      .expectOne(`${API}/courses`)
      .flush({ detail: 'sigue inválido' }, { status: 401, statusText: 'Unauthorized' });

    expect(errorStatus).toBe(401);
    expect(auth.isAuthenticated()).toBe(false);
    expect(navigate).toHaveBeenCalledWith(['/login'], {
      queryParams: { reason: 'session_expired' },
    });
    httpMock.expectNone(`${API}/auth/refresh`);
  });
});
