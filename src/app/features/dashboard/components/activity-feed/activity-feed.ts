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

import { CatalogApi } from '../../../../core/services/catalog-api';
import { LiveFeed, LiveStatus, LiveVerdict, VerdictKind } from '../../../../core/services/live-feed';

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

function initialsOf(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? '')
    .join('');
}

@Component({
  selector: 'app-activity-feed',
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  templateUrl: './activity-feed.html',
  providers: [LiveFeed],
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { class: 'block' },
})
export class ActivityFeed {
  private readonly live = inject(LiveFeed);
  private readonly catalog = inject(CatalogApi);

  private readonly lastVerdict = signal<LiveVerdict | null>(null);
  private readonly names = signal<Record<number, { name: string; code: string | null }>>({});
  private readonly roomCodes = signal<Record<number, string>>({});
  private readonly requested = new Set<number>();

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
      initials: verdict.student_id !== null ? initialsOf(name) : '?',
      code: person?.code ?? null,
      room: this.roomCodes()[verdict.room_id] ?? `Aula #${verdict.room_id}`,
      similarity: Math.round(verdict.similarity * 1000) / 10,
      time: verdict.ts.slice(11, 19),
    };
  });

  constructor() {
    const destroyRef = inject(DestroyRef);
    this.live.connect();
    destroyRef.onDestroy(() => this.live.close());

    this.catalog.rooms({ page_size: 100 }).subscribe({
      next: (page) =>
        this.roomCodes.set(Object.fromEntries(page.items.map((room) => [room.id, room.code]))),
      error: () => undefined,
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
          [studentId]: { name: person.full_name, code: person.code },
        })),
      error: () => undefined,
    });
  }
}
