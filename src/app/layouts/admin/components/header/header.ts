import { ChangeDetectionStrategy, Component, computed, output, signal } from '@angular/core';
import { CUSTOM_ELEMENTS_SCHEMA, DestroyRef } from '@angular/core';
import { NavigationEnd, Router } from '@angular/router';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { filter } from 'rxjs';

interface Crumb {
  label: string;
  url: string | null;
  active: boolean;
}

@Component({
  selector: 'app-header',
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  templateUrl: './header.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class Header {
  readonly toggleSidebarEvent = output<void>();
  private readonly url = signal('');

  readonly breadcrumbs = computed<Crumb[]>(() => {
    const segments = this.url().split('?')[0].split('/').filter(Boolean);
    if (segments[0] !== 'admin') return [{ label: 'Admin', url: '/admin/dashboard', active: true }];
    const page = segments[1] ?? 'dashboard';
    const label = page === 'dashboard' ? 'Dashboard' : page === 'attendance' ? 'Asistencias' : page;
    return [
      { label: 'Admin', url: '/admin/dashboard', active: false },
      { label, url: null, active: true },
    ];
  });

  constructor(
    private readonly router: Router,
    destroyRef: DestroyRef,
  ) {
    this.url.set(router.url);
    router.events
      .pipe(
        filter((e): e is NavigationEnd => e instanceof NavigationEnd),
        takeUntilDestroyed(destroyRef),
      )
      .subscribe((e) => this.url.set(e.urlAfterRedirects));
  }

  toggleSidebar(): void {
    this.toggleSidebarEvent.emit();
  }
}
