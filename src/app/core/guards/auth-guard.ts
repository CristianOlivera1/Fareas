import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { AuthService } from '../services/auth/auth';
import type { UserRole } from '../models/user';

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
  return auth.isAuthenticated() ? router.createUrlTree(['/admin/dashboard']) : true;
};

export const mustChangePasswordGuard: CanActivateFn = () => {
  const auth = inject(AuthService);
  const router = inject(Router);

  if (!auth.isAuthenticated()) {
    return router.createUrlTree(['/login']);
  }

  return auth.mustChangePassword() ? true : router.createUrlTree(['/admin/dashboard']);
};

export function roleGuard(...allowedRoles: UserRole[]): CanActivateFn {
  return () => {
    const auth = inject(AuthService);
    const router = inject(Router);

    if (!auth.isAuthenticated()) {
      return router.createUrlTree(['/login']);
    }

    const userRole = auth.currentUser()?.role;
    if (!userRole || !allowedRoles.includes(userRole)) {
      return router.createUrlTree(['/admin/dashboard']);
    }

    return true;
  };
}
