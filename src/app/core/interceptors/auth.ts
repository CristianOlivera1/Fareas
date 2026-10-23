import { HttpErrorResponse, HttpInterceptorFn, HttpRequest } from '@angular/common/http';
import { inject } from '@angular/core';
import { Router } from '@angular/router';
import { catchError, switchMap, throwError } from 'rxjs';
import { environment } from '../../../environments/environment';
import { AuthService, SessionChangedError } from '../services/auth/auth';

const AUTH_ENDPOINTS = ['/auth/login', '/auth/refresh', '/auth/recover', '/auth/logout'];

function isApiRequest(url: string): boolean {
  return url.startsWith(environment.apiUrl);
}

function isAuthEndpoint(url: string): boolean {
  return AUTH_ENDPOINTS.some((path) => url.includes(path));
}

function isSessionInvalid(status: number): boolean {
  return status === 400 || status === 401 || status === 403 || status === 422;
}

function isPasswordChangeRequired(error: HttpErrorResponse): boolean {
  return error.status === 403 && error.error?.detail?.code === 'must_change_password';
}

function withToken(req: HttpRequest<unknown>, token: string | null): HttpRequest<unknown> {
  return token ? req.clone({ setHeaders: { Authorization: `Bearer ${token}` } }) : req;
}

export const authInterceptor: HttpInterceptorFn = (req, next) => {
  const auth = inject(AuthService);
  const router = inject(Router);

  if (!isApiRequest(req.url) || isAuthEndpoint(req.url)) {
    return next(req);
  }

  return next(withToken(req, auth.accessToken())).pipe(
    catchError((error: HttpErrorResponse) => {
      if (isPasswordChangeRequired(error)) {
        void router.navigate(['/auth/change-password']);
        return throwError(() => error);
      }
      if (error.status !== 401) {
        return throwError(() => error);
      }

      return auth.refreshTokens().pipe(
        catchError((refreshError: HttpErrorResponse) => {
          if (refreshError instanceof SessionChangedError) {
            return throwError(() => refreshError);
          }
          if (isSessionInvalid(refreshError.status)) {
            auth.handleSessionExpired();
          }
          return throwError(() => refreshError);
        }),
        switchMap((tokens) =>
          next(withToken(req, tokens.access_token)).pipe(
            catchError((retryError: HttpErrorResponse) => {
              if (retryError.status === 401) {
                auth.handleSessionExpired();
              }
              return throwError(() => retryError);
            }),
          ),
        ),
      );
    }),
  );
};
