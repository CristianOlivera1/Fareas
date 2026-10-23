import { Injectable, inject, signal } from '@angular/core';

import { environment } from '../../../environments/environment';
import { AuthService } from './auth/auth';

export type VerdictKind =
  | 'asistio'
  | 'tardanza'
  | 'denegado'
  | 'desconocido'
  | 'sin_registro'
  | 'sin_rostro';

export interface LiveVerdict {
  readonly room_id: number;
  readonly verdict: VerdictKind;
  readonly student_id: number | null;
  readonly similarity: number;
  readonly ts: string;
}

export type LiveStatus = 'idle' | 'connecting' | 'live' | 'reconnecting';

const MAX_BACKOFF_MS = 30_000;

@Injectable()
export class LiveFeed {
  private readonly auth = inject(AuthService);

  readonly status = signal<LiveStatus>('idle');
  readonly latest = signal<LiveVerdict | null>(null);

  private source: EventSource | null = null;
  private retryTimer: ReturnType<typeof setTimeout> | null = null;
  private attempt = 0;
  private roomId: number | null = null;
  private active = false;

  connect(roomId: number | null = null): void {
    this.close();
    this.active = true;
    this.roomId = roomId;
    this.open('connecting');
  }

  close(): void {
    this.active = false;
    this.clearRetry();
    this.source?.close();
    this.source = null;
    this.status.set('idle');
  }

  private open(initial: 'connecting' | 'reconnecting'): void {
    const token = this.auth.accessToken();
    if (!token) {
      this.status.set('idle');
      return;
    }
    this.status.set(initial);

    const query = new URLSearchParams({ access_token: token });
    if (this.roomId !== null) query.set('room_id', String(this.roomId));
    const source = new EventSource(`${environment.apiUrl}/dashboard/live?${query}`);
    this.source = source;

    source.onopen = () => {
      this.attempt = 0;
      this.status.set('live');
    };
    source.addEventListener('verdict', (event) => {
      const verdict = this.parse((event as MessageEvent<string>).data);
      if (verdict) this.latest.set(verdict);
    });
    source.onerror = () => this.scheduleReconnect(source);
  }

  private scheduleReconnect(failed: EventSource): void {
    failed.close();
    if (!this.active || this.source !== failed) return;

    this.status.set('reconnecting');
    const delay = Math.min(MAX_BACKOFF_MS, 1000 * 2 ** this.attempt);
    this.attempt += 1;
    this.clearRetry();
    this.retryTimer = setTimeout(() => this.open('reconnecting'), delay);
  }

  private clearRetry(): void {
    if (this.retryTimer) clearTimeout(this.retryTimer);
    this.retryTimer = null;
  }

  private parse(raw: string): LiveVerdict | null {
    try {
      return JSON.parse(raw) as LiveVerdict;
    } catch {
      return null;
    }
  }
}
