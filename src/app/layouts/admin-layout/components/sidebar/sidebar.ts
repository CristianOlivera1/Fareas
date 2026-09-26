import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  OnInit,
  computed,
  signal,
} from '@angular/core';
import { NavigationEnd, Router, RouterModule } from '@angular/router';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { filter } from 'rxjs';
import { CUSTOM_ELEMENTS_SCHEMA } from '@angular/core';
import { NavItem } from '../../../../core/models/user';
import { AuthService } from '../../../../core/services/auth/auth';

@Component({
  selector: 'app-sidebar',
  imports: [RouterModule],
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  templateUrl: './sidebar.html',
  styleUrl: './sidebar.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { '(window:resize)': 'onResize()' },
})
export class Sidebar implements OnInit {
  readonly isOpen = signal(false);
  readonly userMenuOpen = signal(false);
  readonly currentUrl = signal('');

  readonly navItems: NavItem[] = [
    {
      label: 'Dashboard',
      route: '/dashboard',
      icon: 'material-symbols:dashboard-outline',
      tooltip: 'Dashboard',
    },
    {
      label: 'Asistencias',
      route: '/attendance',
      icon: 'material-symbols:fact-check-outline',
      tooltip: 'Asistencias',
    },
  ];

  readonly currentUser = computed(() => this.auth.currentUser());
  readonly userRoleLabel = computed(() =>
    this.currentUser()?.role === 'admin' ? 'Administrador' : 'Asistente',
  );

  constructor(
    private readonly router: Router,
    protected readonly auth: AuthService,
    private readonly destroyRef: DestroyRef,
  ) {
    this.currentUrl.set(this.cleanUrl(this.router.url));
    this.router.events
      .pipe(
        filter((e): e is NavigationEnd => e instanceof NavigationEnd),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe((e) => this.currentUrl.set(this.cleanUrl(e.urlAfterRedirects)));
  }

  ngOnInit(): void {
    this.setInitialState();
  }

  onResize(): void {
    this.setInitialState();
  }

  isActive(route: string): boolean {
    return this.currentUrl() === `/admin${route}`;
  }

  navigateTo(route: string): void {
    void this.router.navigateByUrl(`/admin${route}`);
    this.closeOnMobile();
  }

  toggleSidebar(): void {
    this.isOpen.update((v) => !v);
  }

  closeOnMobile(): void {
    if (window.innerWidth < 768) this.isOpen.set(false);
  }

  toggleUserMenu(): void {
    this.userMenuOpen.update((v) => !v);
  }

  logout(): void {
    this.auth.logout();
    void this.router.navigate(['/login']);
  }

  private setInitialState(): void {
    this.isOpen.set(window.innerWidth >= 768);
  }

  private cleanUrl(url: string): string {
    return url.split('?')[0].split('#')[0];
  }
}
