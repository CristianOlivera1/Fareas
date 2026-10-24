import {
  ChangeDetectionStrategy,
  Component,
  CUSTOM_ELEMENTS_SCHEMA,
  DestroyRef,
  ElementRef,
  HostListener,
  computed,
  inject,
  signal,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { Router } from '@angular/router';
import { catchError, interval, of, startWith, switchMap } from 'rxjs';

import type { AppNotification } from '../../../../core/models/notification';
import { NotificationsApi } from '../../../../core/services/notifications-api';

const KIND_ICONS: Record<string, string> = {
  dpi: 'material-symbols:warning-outline',
  dpi_limite: 'material-symbols:person-alert',
  justificacion: 'material-symbols:medical-information-outline',
  clase_cancelada: 'material-symbols:event-busy-outline',
  sesion_revision: 'material-symbols:fact-check-outline',
  rectificacion: 'material-symbols:edit-note',
  dispositivo_offline: 'material-symbols:videocam-off-outline',
};

const SEVERITY_CLASSES: Record<string, string> = {
  info: 'bg-blue-50 text-blue-600',
  success: 'bg-emerald-50 text-emerald-600',
  warning: 'bg-amber-50 text-amber-600',
  danger: 'bg-red-50 text-red-600',
};

@Component({
  selector: 'app-notifications-bell',
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  templateUrl: './notifications-bell.html',
  styleUrl: './notifications-bell.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { class: 'block' },
})
export class NotificationsBell {
  private readonly api = inject(NotificationsApi);
  private readonly router = inject(Router);
  private readonly elementRef = inject(ElementRef<HTMLElement>);
  private readonly destroyRef = inject(DestroyRef);

  readonly open = signal(false);
  readonly loading = signal(false);
  readonly markingAll = signal(false);
  readonly items = signal<AppNotification[]>([]);
  readonly unread = signal(0);
  readonly error = signal<string | null>(null);

  readonly badge = computed(() => (this.unread() > 99 ? '99+' : String(this.unread())));

  constructor() {
    interval(10_000)
      .pipe(
        startWith(0),
        switchMap(() => this.api.unreadCount().pipe(catchError(() => of(null)))),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe((res) => {
        if (res) this.unread.set(res.count);
      });
  }

  toggle(): void {
    const next = !this.open();
    this.open.set(next);
    if (next) this.loadList();
  }

  close(): void {
    this.open.set(false);
  }

  loadList(): void {
    this.loading.set(true);
    this.error.set(null);
    this.api
      .list({ limit: 30 })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (res) => {
          this.items.set(res.items);
          this.unread.set(res.unread);
          this.loading.set(false);
        },
        error: () => {
          this.error.set('No se pudieron cargar las notificaciones.');
          this.loading.set(false);
        },
      });
  }

  openItem(notification: AppNotification): void {
    if (!notification.read) {
      this.api
        .markRead(notification.id)
        .pipe(takeUntilDestroyed(this.destroyRef))
        .subscribe((res) => {
          this.unread.set(res.count);
          this.items.update((items) =>
            items.map((item) => (item.id === notification.id ? { ...item, read: true } : item)),
          );
        });
    }
    this.close();
    if (notification.link) void this.router.navigateByUrl(notification.link);
  }

  markAll(): void {
    if (this.markingAll() || this.unread() === 0) return;
    this.markingAll.set(true);
    this.api
      .markAllRead()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: () => {
          this.unread.set(0);
          this.items.update((items) => items.map((item) => ({ ...item, read: true })));
          this.markingAll.set(false);
        },
        error: () => this.markingAll.set(false),
      });
  }

  iconFor(kind: string): string {
    return KIND_ICONS[kind] ?? 'material-symbols:notifications-outline';
  }

  toneFor(severity: string): string {
    return SEVERITY_CLASSES[severity] ?? SEVERITY_CLASSES['info'];
  }

  relative(value: string): string {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return '';
    const diff = Date.now() - date.getTime();
    if (diff < 60_000) return 'ahora';
    if (diff < 3_600_000) return `hace ${Math.floor(diff / 60_000)} min`;
    if (diff < 86_400_000) return `hace ${Math.floor(diff / 3_600_000)} h`;
    if (diff < 604_800_000) return `hace ${Math.floor(diff / 86_400_000)} d`;
    return new Intl.DateTimeFormat('es-PE', { day: '2-digit', month: 'short' }).format(date);
  }

  @HostListener('document:click', ['$event'])
  onDocumentClick(event: MouseEvent): void {
    if (
      this.open() &&
      this.elementRef.nativeElement &&
      !this.elementRef.nativeElement.contains(event.target as Node)
    ) {
      this.close();
    }
  }

  @HostListener('document:keydown.escape')
  onEscape(): void {
    this.close();
  }
}
