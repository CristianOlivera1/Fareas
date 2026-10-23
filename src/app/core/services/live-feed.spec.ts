import { TestBed } from '@angular/core/testing';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { AuthService } from './auth/auth';
import { LiveFeed } from './live-feed';

class FakeEventSource {
  static instances: FakeEventSource[] = [];
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  closed = false;
  private readonly listeners = new Map<string, (event: MessageEvent<string>) => void>();

  constructor(readonly url: string) {
    FakeEventSource.instances.push(this);
  }

  addEventListener(type: string, listener: (event: MessageEvent<string>) => void): void {
    this.listeners.set(type, listener);
  }

  emit(type: string, data: string): void {
    this.listeners.get(type)?.({ data } as MessageEvent<string>);
  }

  close(): void {
    this.closed = true;
  }
}

describe('LiveFeed', () => {
  let feed: LiveFeed;

  beforeEach(() => {
    vi.useFakeTimers();
    FakeEventSource.instances = [];
    vi.stubGlobal('EventSource', FakeEventSource);
    TestBed.configureTestingModule({
      providers: [LiveFeed, { provide: AuthService, useValue: { accessToken: () => 'token-123456' } }],
    });
    feed = TestBed.inject(LiveFeed);
  });

  afterEach(() => {
    feed.close();
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('opens the stream with the token and publishes verdicts', () => {
    feed.connect(4);
    const source = FakeEventSource.instances[0];
    expect(source.url).toContain('/dashboard/live?access_token=token-123456&room_id=4');

    source.onopen?.();
    expect(feed.status()).toBe('live');

    source.emit('verdict', JSON.stringify({ room_id: 4, verdict: 'asistio', student_id: 7, similarity: 0.62, ts: '2026-10-23T09:00:00' }));
    expect(feed.latest()?.student_id).toBe(7);
  });

  it('ignores malformed events', () => {
    feed.connect();
    FakeEventSource.instances[0].emit('verdict', 'not-json');
    expect(feed.latest()).toBeNull();
  });

  it('reconnects with backoff after an error', () => {
    feed.connect();
    FakeEventSource.instances[0].onerror?.();
    expect(feed.status()).toBe('reconnecting');
    expect(FakeEventSource.instances[0].closed).toBe(true);

    vi.advanceTimersByTime(1000);
    expect(FakeEventSource.instances).toHaveLength(2);

    FakeEventSource.instances[1].onerror?.();
    vi.advanceTimersByTime(1999);
    expect(FakeEventSource.instances).toHaveLength(2);
    vi.advanceTimersByTime(1);
    expect(FakeEventSource.instances).toHaveLength(3);
  });

  it('stops reconnecting after close', () => {
    feed.connect();
    const source = FakeEventSource.instances[0];
    feed.close();
    source.onerror?.();
    vi.advanceTimersByTime(60_000);
    expect(FakeEventSource.instances).toHaveLength(1);
    expect(feed.status()).toBe('idle');
  });
});
