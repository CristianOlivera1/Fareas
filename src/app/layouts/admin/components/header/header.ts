import { ChangeDetectionStrategy, Component, computed, inject, output, signal } from '@angular/core';
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
  private readonly router = inject(Router);
  private readonly url = signal('');
  private readonly routeTitle = signal<string | null>(null);

  readonly breadcrumbs = computed<Crumb[]>(() => {
    const segments = this.url().split('?')[0].split('/').filter(Boolean);
    if (segments[0] !== 'admin') return [{ label: 'Panel', url: '/admin/dashboard', active: true }];
    const page = this.routeTitle() ?? segments[1] ?? 'dashboard';
    return [
      { label: 'Panel', url: '/admin/dashboard', active: false },
      { label: page, url: null, active: true },
    ];
  });

  constructor(destroyRef: DestroyRef) {
    this.url.set(this.router.url);
    this.pullTitle();
    this.router.events
      .pipe(
        filter((e): e is NavigationEnd => e instanceof NavigationEnd),
        takeUntilDestroyed(destroyRef),
      )
      .subscribe((e) => {
        this.url.set(e.urlAfterRedirects);
        this.pullTitle();
      });
  }

  private pullTitle(): void {
    let title: string | null = null;
    let current: import('@angular/router').ActivatedRoute | null = this.router.routerState.root;
    while (current) {
      const value = current.snapshot?.data?.['title'] as string | undefined;
      if (value) title = value;
      current = current.firstChild;
    }
    this.routeTitle.set(title);
  }

  toggleSidebar(): void {
    this.toggleSidebarEvent.emit();
  }
}
