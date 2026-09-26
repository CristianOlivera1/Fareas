import { Routes } from '@angular/router';
import { authGuard, loginGuard } from './core/guards/auth-guard';

export const routes: Routes = [
  {
    path: '',
    redirectTo: '/login',
    pathMatch: 'full',
  },
  {
    path: 'login',
    loadComponent: () => import('./features/auth/login/login').then((m) => m.Login),
    canActivate: [loginGuard],
  },
  {
    path: 'admin',
    loadComponent: () => import('./layouts/admin/admin').then((m) => m.AdminLayout),
    canActivate: [authGuard],
    children: [
      {
        path: '',
        redirectTo: 'dashboard',
        pathMatch: 'full',
      },
      {
        path: 'dashboard',
        loadComponent: () =>
          import('./features/dashboard/dashboard').then((m) => m.Dashboard),
      },
      {
        path: 'attendance',
        loadComponent: () =>
          import('./features/attendance/attendance').then((m) => m.Attendance),
      },
    ],
  },
  {
    path: '**',
    redirectTo: '/login',
    pathMatch: 'full',
  },
];
