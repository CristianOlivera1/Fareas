import { HttpClient, HttpParams } from '@angular/common/http';
import { inject } from '@angular/core';

import { environment } from '../../../environments/environment';

/** URL base de la API: en desarrollo apunta al backend FastAPI (puerto 8000);
 * en producción el build de Angular se sirve desde el PROPIO FastAPI (PLAN-FRONTEND F8),
 * así que basta la ruta relativa /api/v1 (un solo origen, sin CORS). */
export function apiUrl(path = ''): string {
  return `${environment.apiUrl}${path}`;
}

/** Página del backend (schemas/common.py → Page[T]). */
export interface Page<T> {
  readonly items: T[];
  readonly total: number;
  readonly page: number;
  readonly page_size: number;
}

/** Parámetros comunes de listado (core/pagination.py). */
export interface ListParams {
  readonly page?: number;
  readonly page_size?: number;
  readonly q?: string | null;
  readonly [key: string]: unknown;
}

/** Serializa ListParams → HttpParams (ignora null/undefined/''). */
export function toParams(params?: ListParams): HttpParams {
  let http = new HttpParams();
  for (const [key, value] of Object.entries(params ?? {})) {
    if (value === null || value === undefined || value === '') continue;
    http = http.set(key, String(value));
  }
  return http;
}

/** Helper base para services de listados paginados (F2-F6 lo reutilizan). */
export abstract class BaseApi {
  protected readonly http = inject(HttpClient);

  protected get<T>(path: string, params?: ListParams) {
    return this.http.get<T>(apiUrl(path), { params: toParams(params) });
  }

  protected post<T>(path: string, body?: unknown) {
    return this.http.post<T>(apiUrl(path), body ?? {});
  }

  protected patch<T>(path: string, body: unknown) {
    return this.http.patch<T>(apiUrl(path), body);
  }

  protected delete<T>(path: string) {
    return this.http.delete<T>(apiUrl(path));
  }
}
