import { Injectable, computed, inject, signal } from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';
import { toParams } from '../../core/api/api-url';

@Injectable({ providedIn: 'root' })
export class QueryParams {
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);

  private readonly raw = signal<Record<string, string | string[]>>(this.readCurrent());

  constructor() {
    this.router.events.subscribe(() => this.raw.set(this.readCurrent()));
  }

  readonly all = computed(() => this.raw());

  filter(name: string) {
    return computed(() => {
      const v = this.raw()[name];
      return typeof v === 'string' && v !== '' ? v : null;
    });
  }

  number(name: string, fallback: number) {
    return computed(() => {
      const v = this.raw()[name];
      if (typeof v !== 'string' || v === '') return fallback;
      const parsed = Number(v);
      return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
    });
  }

  boolean(name: string) {
    return computed(() => {
      const v = this.raw()[name];
      return typeof v === 'string' && ['1', 'true', 'on'].includes(v);
    });
  }

  async update(patch: Record<string, string | number | boolean | null | undefined>): Promise<void> {
    const current: Record<string, string | string[]> = { ...this.raw() };

    for (const [key, value] of Object.entries(patch)) {
      if (value === null || value === undefined || value === '') {
        delete current[key];
      } else {
        current[key] = String(value);
      }
    }
    if (current['page'] === '1') delete current['page'];

    await this.router.navigate([], {
      relativeTo: this.route,
      queryParams: current,
      queryParamsHandling: '',
    });
  }

  toHttpParams(extra?: Record<string, string | number | null | undefined>) {
    const merged: Record<string, string | number | null | undefined> = {};
    for (const [k, v] of Object.entries(this.raw())) {
      merged[k] = typeof v === 'string' ? v : v.join(',');
    }
    Object.assign(merged, extra);
    return toParams(merged);
  }

  private readCurrent(): Record<string, string | string[]> {
    const params = this.router.parseUrl(this.router.url).queryParamMap;
    const out: Record<string, string | string[]> = {};
    for (const key of params.keys) {
      const values = params.getAll(key);
      out[key] = values.length > 1 ? values : (values[0] ?? '');
    }
    return out;
  }
}
