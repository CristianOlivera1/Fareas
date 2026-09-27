import { Routes } from '@angular/router';
import { authGuard, loginGuard, mustChangePasswordGuard, roleGuard } from './core/guards/auth-guard';

/** Página placeholder (F1): cada bloque posterior reemplaza loadComponent. */
const pendiente = (title: string, placeholder: string) => ({
  loadComponent: () => import('./features/placeholder/placeholder').then((m) => m.PlaceholderPage),
  data: { title, placeholder },
});

export const routes: Routes = [
  {
    path: '',
    redirectTo: '/login',
    pathMatch: 'full',
  },
  {
    path: 'login',
    loadComponent: () => import('./layouts/auth/auth').then((m) => m.AuthLayout),
    canActivate: [loginGuard],
    children: [
      {
        path: '',
        loadComponent: () => import('./features/auth/login/login').then((m) => m.Login),
      },
    ],
  },
  {
    path: 'auth/recover',
    loadComponent: () => import('./layouts/auth/auth').then((m) => m.AuthLayout),
    children: [
      {
        path: '',
        loadComponent: () =>
          import('./features/auth/recover-password/recover-password').then(
            (m) => m.RecoverPassword,
          ),
      },
    ],
  },
  {
    path: 'auth/change-password',
    loadComponent: () => import('./layouts/auth/auth').then((m) => m.AuthLayout),
    canActivate: [mustChangePasswordGuard],
    children: [
      {
        path: '',
        loadComponent: () =>
          import('./features/auth/change-password/change-password').then(
            (m) => m.ChangePassword,
          ),
      },
    ],
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
        data: { title: 'Dashboard' },
      },
      {
        path: 'attendance',
        loadComponent: () =>
          import('./features/attendance/attendance').then((m) => m.Attendance),
        data: { title: 'Asistencias' },
      },

      // --- Académico (F2) ---
      { path: 'courses', canActivate: [roleGuard('admin', 'docente')], ...pendiente('Cursos y grupos', 'F2 · Académico') },
      { path: 'enrollments', canActivate: [roleGuard('admin', 'docente')], ...pendiente('Matrículas', 'F2 · Académico') },

      // --- Catálogo (F2) ---
      { path: 'teachers', canActivate: [roleGuard('admin')], ...pendiente('Docentes', 'F2 · Catálogo') },
      { path: 'students', canActivate: [roleGuard('admin', 'docente')], ...pendiente('Estudiantes', 'F2 · Catálogo') },
      { path: 'rooms', canActivate: [roleGuard('admin')], ...pendiente('Aulas', 'F2 · Catálogo') },
      { path: 'devices', canActivate: [roleGuard('admin')], ...pendiente('Dispositivos', 'F2 · Catálogo') },

      // --- Calendario (F3) ---
      { path: 'calendar/holidays', canActivate: [roleGuard('admin', 'docente')], ...pendiente('Feriados', 'F3 · Calendario') },
      { path: 'calendar/justifications', canActivate: [roleGuard('admin', 'docente')], ...pendiente('Justificaciones', 'F3 · Calendario') },
      { path: 'calendar/settings', canActivate: [roleGuard('admin')], ...pendiente('Parámetros del sistema', 'F3 · Calendario') },

      // --- Herramientas (F4-F6) ---
      { path: 'faces', canActivate: [roleGuard('admin')], ...pendiente('Enrolamiento facial', 'F4 · Herramientas') },
      { path: 'imports', canActivate: [roleGuard('admin')], ...pendiente('Importar horario (PDF)', 'F6 · Herramientas') },
      { path: 'reports', canActivate: [roleGuard('admin', 'docente')], ...pendiente('Reportes', 'F6 · Herramientas') },
      { path: 'audit', canActivate: [roleGuard('admin')], ...pendiente('Bitácora', 'F6 · Herramientas') },
    ],
  },
  {
    path: '**',
    redirectTo: '/login',
    pathMatch: 'full',
  },
];
