import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { MessageService } from 'primeng/api';
import { AuthService } from '../services/auth/auth';
import { ROLE_HOME, rolesForRoute } from '../constants/nav';
import type { UserRole } from '../models/user';

function homeFor(role: UserRole | undefined): string {
  return role ? ROLE_HOME[role] : '/login';
}

export const authGuard: CanActivateFn = () => {
  const auth = inject(AuthService);
  const router = inject(Router);

  if (!auth.isAuthenticated()) {
    return router.createUrlTree(['/login']);
  }

  if (auth.mustChangePassword()) {
    return router.createUrlTree(['/auth/change-password']);
  }

  return true;
};

export const loginGuard: CanActivateFn = () => {
  const auth = inject(AuthService);
  const router = inject(Router);
  return auth.isAuthenticated() ? router.createUrlTree([homeFor(auth.currentUser()?.role)]) : true;
};

export const mustChangePasswordGuard: CanActivateFn = () => {
  const auth = inject(AuthService);
  const router = inject(Router);

  if (!auth.isAuthenticated()) {
    return router.createUrlTree(['/login']);
  }

  return auth.mustChangePassword()
    ? true
    : router.createUrlTree([homeFor(auth.currentUser()?.role)]);
};

export function roleGuard(...allowedRoles: UserRole[]): CanActivateFn {
  return () => {
    const auth = inject(AuthService);
    const router = inject(Router);
    const toast = inject(MessageService);

    if (!auth.isAuthenticated()) {
      return router.createUrlTree(['/login']);
    }

    const userRole = auth.currentUser()?.role;
    if (userRole && allowedRoles.includes(userRole)) {
      return true;
    }

    toast.add({
      severity: 'warn',
      summary: 'Acceso restringido',
      detail: 'No tienes acceso a esa sección.',
    });
    return router.createUrlTree([homeFor(userRole)]);
  };
}

export const navGuard = (route: string): CanActivateFn => roleGuard(...rolesForRoute(route));
