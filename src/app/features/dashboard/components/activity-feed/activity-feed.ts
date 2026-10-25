import {
  ChangeDetectionStrategy,
  Component,
  CUSTOM_ELEMENTS_SCHEMA,
  DestroyRef,
  computed,
  effect,
  inject,
  signal,
  untracked,
} from '@angular/core';
import { forkJoin } from 'rxjs';

import { environment } from '../../../../../environments/environment';
import { AuthService } from '../../../../core/services/auth/auth';
import { CalendarApi } from '../../../../core/services/calendar-api';
import { CatalogApi } from '../../../../core/services/catalog-api';
import { LiveFeed, LiveStatus, LiveVerdict, VerdictKind } from '../../../../core/services/live-feed';
import { Avatar } from '../../../../shared/components/avatar/avatar';

interface VerdictStyle {
  readonly label: string;
  readonly message: string;
  readonly dot: string;
  readonly border: string;
  readonly badge: string;
}

type DisplayVerdict = Exclude<VerdictKind, 'sin_rostro'>;

const VERDICT_STYLES: Record<DisplayVerdict, VerdictStyle> = {
  asistio: {
    label: 'Asistió',
    message: 'Registro correcto',
    dot: 'bg-green-500',
    border: 'border-green-400',
    badge: 'bg-green-500',
  },
  tardanza: {
    label: 'Tardanza',
    message: 'Registro con tardanza',
    dot: 'bg-amber-500',
    border: 'border-amber-400',
    badge: 'bg-amber-500',
  },
  denegado: {
    label: 'Acceso denegado',
    message: 'No matriculado en esta aula',
    dot: 'bg-red-500',
    border: 'border-red-400',
    badge: 'bg-red-500',
  },
  desconocido: {
    label: 'Desconocido',
    message: 'Rostro no identificado',
    dot: 'bg-blue-500',
    border: 'border-blue-400',
    badge: 'bg-blue-500',
  },
  sin_registro: {
    label: 'Sin registro',
    message: 'No hay clase activa',
    dot: 'bg-gray-400',
    border: 'border-gray-400',
    badge: 'bg-gray-500',
  },
};

const STATUS_TEXT: Record<LiveStatus, { label: string; dot: string }> = {
  idle: { label: 'Sin conexión', dot: 'bg-gray-400' },
  connecting: { label: 'Conectando…', dot: 'bg-amber-400 animate-pulse' },
  live: { label: 'En vivo', dot: 'bg-green-500 animate-pulse' },
  reconnecting: { label: 'Reconectando…', dot: 'bg-amber-400 animate-pulse' },
};

@Component({
  selector: 'app-activity-feed',
  imports: [Avatar],
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  templateUrl: './activity-feed.html',
  providers: [LiveFeed],
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { class: 'block' },
})
export class ActivityFeed {
  private readonly live = inject(LiveFeed);
  private readonly catalog = inject(CatalogApi);
  private readonly calendar = inject(CalendarApi);
  private readonly auth = inject(AuthService);

  private readonly lastVerdict = signal<LiveVerdict | null>(null);
  private readonly names = signal<
    Record<number, { name: string; code: string | null; avatarUrl: string | null }>
  >({});
  private readonly roomCodes = signal<Record<number, string>>({});
  private readonly requested = new Set<number>();

  readonly cameraRooms = signal<Record<number, string>>({});
  readonly camerasLoaded = signal(false);
  readonly roomId = signal<number | null>(null);
  readonly hasCameras = computed(() => Object.keys(this.cameraRooms()).length > 0);
  readonly roomLabel = computed(() => {
    const room = this.roomId();
    return room === null ? null : (this.cameraRooms()[room] ?? null);
  });

  readonly streamFailed = signal(false);
  readonly streamUrl = computed(() => {
    const room = this.roomId();
    const token = this.auth.accessToken();
    if (room === null || !token) return null;
    return `${environment.apiUrl}/dashboard/camera/${room}/mjpeg?access_token=${encodeURIComponent(token)}`;
  });

  readonly connection = computed(() => STATUS_TEXT[this.live.status()]);

  readonly entry = computed(() => {
    const verdict = this.lastVerdict();
    if (!verdict || verdict.verdict === 'sin_rostro') return null;
    const person = verdict.student_id !== null ? this.names()[verdict.student_id] : undefined;
    const name =
      person?.name ??
      (verdict.student_id !== null ? `Estudiante #${verdict.student_id}` : 'Persona no identificada');
    return {
      style: VERDICT_STYLES[verdict.verdict],
      name,
      studentId: verdict.student_id,
      avatarUrl: person?.avatarUrl ?? null,
      code: person?.code ?? null,
      room: this.roomCodes()[verdict.room_id] ?? `Aula #${verdict.room_id}`,
      similarity: Math.round(verdict.similarity * 1000) / 10,
      time: verdict.ts.slice(11, 19),
    };
  });

  constructor() {
    const destroyRef = inject(DestroyRef);
    destroyRef.onDestroy(() => this.live.close());

    forkJoin({
      settings: this.calendar.settings(),
      devices: this.catalog.devices({ device_type: 'camara', page_size: 100 }),
    }).subscribe({
      next: ({ settings, devices }) => {
        const rooms: Record<number, string> = {};
        for (const device of devices.items) {
          if (device.is_active) rooms[device.room_id] = device.room_code ?? `Aula #${device.room_id}`;
        }
        this.cameraRooms.set(rooms);
        const configured = settings.live_room_id ?? null;
        const fallback = Number(Object.keys(rooms)[0] ?? NaN);
        this.roomId.set(
          configured !== null && configured in rooms ? configured : Number.isNaN(fallback) ? null : fallback,
        );
        this.camerasLoaded.set(true);
      },
      error: () => this.camerasLoaded.set(true),
    });

    this.catalog.rooms({ page_size: 100 }).subscribe({
      next: (page) =>
        this.roomCodes.set(Object.fromEntries(page.items.map((room) => [room.id, room.code]))),
      error: () => undefined,
    });

    effect(() => {
      const room = this.roomId();
      untracked(() => {
        this.lastVerdict.set(null);
        this.streamFailed.set(false);
        if (room === null) this.live.close();
        else this.live.connect(room);
      });
    });

    effect(() => {
      const verdict = this.live.latest();
      if (!verdict || verdict.verdict === 'sin_rostro') return;
      this.lastVerdict.set(verdict);
      untracked(() => this.resolveName(verdict.student_id));
    });
  }

  private resolveName(studentId: number | null): void {
    if (studentId === null || this.requested.has(studentId)) return;
    this.requested.add(studentId);
    this.catalog.account(studentId).subscribe({
      next: (person) =>
        this.names.update((current) => ({
          ...current,
          [studentId]: {
            name: person.full_name,
            code: person.code,
            avatarUrl: person.avatar_url ?? null,
          },
        })),
      error: () => undefined,
    });
  }
}
