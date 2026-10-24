import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  OnInit,
  computed,
  signal,
  ElementRef,
  ViewChild,
  effect,
} from '@angular/core';
import { NavigationEnd, Router, RouterModule } from '@angular/router';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { filter } from 'rxjs';
import { CUSTOM_ELEMENTS_SCHEMA } from '@angular/core';
import { ROLE_LABELS } from '../../../../core/models/user';
import { AuthService } from '../../../../core/services/auth/auth';
import { Avatar } from '../../../../shared/components/avatar/avatar';
import { ADMIN_PREFIX, ROLE_HOME, navForRole, type NavEntry } from '../../../../core/constants/nav';

@Component({
  selector: 'app-sidebar',
  imports: [RouterModule, Avatar],
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  templateUrl: './sidebar.html',
  styleUrl: './sidebar.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: {
    '(window:resize)': 'onResize()',
    '(document:click)': 'onClickOutside($event)',
  },
})
export class Sidebar implements OnInit {
  readonly isOpen = signal(false);
  readonly userMenuOpen = signal(false);
  readonly currentUrl = signal('');

  readonly openGroups = signal<Set<string>>(new Set());

  @ViewChild('userMenuContainer') userMenuContainer?: ElementRef<HTMLElement>;

  readonly entries = computed<NavEntry[]>(() => navForRole(this.auth.currentUser()?.role));

  readonly currentUser = computed(() => this.auth.currentUser());
  readonly homeRoute = computed(() => {
    const role = this.currentUser()?.role;
    return role ? ROLE_HOME[role] : ADMIN_PREFIX;
  });
  readonly userRoleLabel = computed(() => {
    const role = this.currentUser()?.role;
    return role ? ROLE_LABELS[role] : 'Sin rol';
  });

  constructor(
    private readonly router: Router,
    protected readonly auth: AuthService,
    private readonly destroyRef: DestroyRef,
  ) {
    this.currentUrl.set(this.cleanUrl(this.router.url));
    effect(() => {
      const groupLabels = this.entries()
        .filter((entry) => 'children' in entry && entry.children)
        .map((entry) => entry.label);
      this.openGroups.set(new Set(groupLabels));
    });
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

  onClickOutside(event: Event): void {
    if (
      this.userMenuOpen() &&
      this.userMenuContainer?.nativeElement &&
      !this.userMenuContainer.nativeElement.contains(event.target as Node)
    ) {
      this.userMenuOpen.set(false);
    }
  }

  isActive(route: string): boolean {
    const target = `${ADMIN_PREFIX}${route}`;
    const url = this.currentUrl();
    return url === target || url.startsWith(`${target}/`);
  }

  groupContains(group: NavEntry): boolean {
    if (!('children' in group) || !group.children) return false;
    return group.children.some((c) => this.isActive(c.route));
  }

  navigateTo(route: string): void {
    void this.router.navigateByUrl(`${ADMIN_PREFIX}${route}`);
    this.closeOnMobile();
  }

  toggleGroup(label: string): void {
    this.openGroups.update((current) => {
      const next = new Set(current);
      if (!next.delete(label)) next.add(label);
      return next;
    });
  }

  isGroupOpen(label: string): boolean {
    return this.openGroups().has(label);
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

  closeUserMenu(): void {
    this.userMenuOpen.set(false);
    this.closeOnMobile();
  }

  logout(): void {
    this.auth.logout();
  }

  private setInitialState(): void {
    this.isOpen.set(window.innerWidth >= 768);
  }

  private cleanUrl(url: string): string {
    return url.split('?')[0].split('#')[0];
  }
}
