import { ChangeDetectionStrategy, Component, CUSTOM_ELEMENTS_SCHEMA, computed, inject } from '@angular/core';
import { RouterLink } from '@angular/router';
import { ROLE_HOME } from '../../core/constants/nav';
import { AuthService } from '../../core/services/auth/auth';

@Component({
  selector: 'app-not-found-page',
  imports: [RouterLink],
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  template: `
    <main class="flex min-h-dvh items-center justify-center bg-gray-50 px-4">
      <div class="max-w-md rounded-2xl border border-gray-100 bg-white p-10 text-center">
        <iconify-icon icon="material-symbols:explore-off-outline" width="40" class="text-gray-300"></iconify-icon>
        <h1 class="mt-3 text-xl font-semibold tracking-tight text-gray-900">Página no encontrada</h1>
        <p class="mt-1 text-sm text-gray-500">La dirección que buscas no existe o fue movida.</p>
        <a [routerLink]="homeRoute()" class="mt-6 inline-flex rounded-xl bg-(--fareas-primary) px-4 py-2 text-sm font-medium text-white">
          {{ isAuthenticated() ? 'Volver al inicio' : 'Ir a iniciar sesión' }}
        </a>
      </div>
    </main>
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class NotFoundPage {
  private readonly auth = inject(AuthService);

  readonly isAuthenticated = this.auth.isAuthenticated;
  readonly homeRoute = computed(() => {
    const role = this.auth.currentUser()?.role;
    return this.isAuthenticated() && role ? ROLE_HOME[role] : '/login';
  });
}
