import { Routes } from '@angular/router';
import { authGuard, loginGuard, mustChangePasswordGuard, roleGuard } from './core/guards/auth-guard';

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

      {
        path: 'schedule',
        canActivate: [roleGuard('admin', 'docente')],
        loadComponent: () =>
          import('./features/schedule/schedule-general/schedule-general').then(
            (m) => m.ScheduleGeneralPage,
          ),
        data: { title: 'Horario general' },
      },
      {
        path: 'courses',
        canActivate: [roleGuard('admin', 'docente')],
        loadComponent: () => import('./features/courses/courses/courses').then((m) => m.CoursesPage),
        data: { title: 'Cursos y grupos' },
      },
      {
        path: 'courses/:courseId',
        canActivate: [roleGuard('admin', 'docente')],
        loadComponent: () =>
          import('./features/courses/course-detail/course-detail').then((m) => m.CourseDetailPage),
        data: { title: 'Grupos y horario' },
      },
      {
        path: 'enrollments',
        canActivate: [roleGuard('admin', 'docente')],
        loadComponent: () =>
          import('./features/enrollments/enrollments/enrollments').then((m) => m.EnrollmentsPage),
        data: { title: 'Matrículas' },
      },

      {
        path: 'teachers',
        canActivate: [roleGuard('admin')],
        loadComponent: () => import('./features/catalog/teachers/teachers').then((m) => m.TeachersPage),
        data: { title: 'Docentes' },
      },
      {
        path: 'students',
        canActivate: [roleGuard('admin', 'docente')],
        loadComponent: () => import('./features/catalog/students/students').then((m) => m.StudentsPage),
        data: { title: 'Estudiantes' },
      },
      {
        path: 'rooms',
        canActivate: [roleGuard('admin')],
        loadComponent: () => import('./features/catalog/rooms/rooms').then((m) => m.RoomsPage),
        data: { title: 'Aulas' },
      },
      {
        path: 'devices',
        canActivate: [roleGuard('admin')],
        loadComponent: () => import('./features/catalog/devices/devices').then((m) => m.DevicesPage),
        data: { title: 'Dispositivos' },
      },

      {
        path: 'calendar/holidays',
        canActivate: [roleGuard('admin', 'docente')],
        loadComponent: () =>
          import('./features/calendar/holidays/holidays.page').then((m) => m.HolidaysPage),
        data: { title: 'Feriados' },
      },
      {
        path: 'calendar/justifications',
        canActivate: [roleGuard('admin', 'docente')],
        loadComponent: () =>
          import('./features/calendar/justifications/justifications.page').then(
            (m) => m.JustificationsPage,
          ),
        data: { title: 'Justificaciones' },
      },
      {
        path: 'calendar/settings',
        canActivate: [roleGuard('admin')],
        loadComponent: () =>
          import('./features/calendar/settings/settings.page').then((m) => m.SettingsPage),
        data: { title: 'Parámetros del sistema' },
      },

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
