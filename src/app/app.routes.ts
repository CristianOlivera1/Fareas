import { Routes } from '@angular/router';
import { authGuard, loginGuard, mustChangePasswordGuard, navGuard } from './core/guards/auth-guard';

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
        canActivate: [navGuard('/dashboard')],
        loadComponent: () =>
          import('./features/dashboard/dashboard').then((m) => m.Dashboard),
        data: { title: 'Dashboard' },
      },
      {
        path: 'attendance',
        canActivate: [navGuard('/attendance')],
        loadComponent: () =>
          import('./features/attendance/attendance').then((m) => m.Attendance),
        data: { title: 'Asistencias' },
      },
      {
        path: 'me',
        canActivate: [navGuard('/me')],
        loadComponent: () =>
          import('./features/student-home/student-home').then((m) => m.StudentHomePage),
        data: { title: 'Inicio' },
      },
      {
        path: 'my-attendance',
        canActivate: [navGuard('/my-attendance')],
        loadComponent: () =>
          import('./features/my-attendance/my-attendance').then((m) => m.MyAttendancePage),
        data: { title: 'Mis asistencias' },
      },
      {
        path: 'my-schedule',
        canActivate: [navGuard('/my-schedule')],
        loadComponent: () =>
          import('./features/my-schedule/my-schedule').then((m) => m.MySchedulePage),
        data: { title: 'Mi horario' },
      },
      {
        path: 'my-enrollment',
        canActivate: [navGuard('/my-enrollment')],
        loadComponent: () =>
          import('./features/my-enrollment/my-enrollment').then((m) => m.MyEnrollmentPage),
        data: { title: 'Mi matrícula' },
      },
      {
        path: 'my-justifications',
        canActivate: [navGuard('/my-justifications')],
        loadComponent: () =>
          import('./features/my-justifications/my-justifications').then((m) => m.MyJustificationsPage),
        data: { title: 'Mis justificaciones' },
      },
      {
        path: 'my-groups',
        canActivate: [navGuard('/my-groups')],
        loadComponent: () =>
          import('./features/my-groups/my-groups').then((m) => m.MyGroupsPage),
        data: { title: 'Mis grupos' },
      },
      {
        path: 'at-risk',
        canActivate: [navGuard('/at-risk')],
        loadComponent: () => import('./features/at-risk/at-risk').then((m) => m.AtRiskPage),
        data: { title: 'Alumnos en riesgo' },
      },
      {
        path: 'profile',
        loadComponent: () =>
          import('./features/profile/profile/profile').then((m) => m.ProfilePage),
        data: { title: 'Mi perfil' },
      },

      {
        path: 'schedule',
        canActivate: [navGuard('/schedule')],
        loadComponent: () =>
          import('./features/schedule/schedule-general/schedule-general').then(
            (m) => m.ScheduleGeneralPage,
          ),
        data: { title: 'Horario general' },
      },
      {
        path: 'courses',
        canActivate: [navGuard('/courses')],
        loadComponent: () => import('./features/courses/courses/courses').then((m) => m.CoursesPage),
        data: { title: 'Cursos y grupos' },
      },
      {
        path: 'courses/:courseId',
        canActivate: [navGuard('/courses')],
        loadComponent: () =>
          import('./features/courses/course-detail/course-detail').then((m) => m.CourseDetailPage),
        data: { title: 'Grupos y horario' },
      },
      {
        path: 'enrollments',
        canActivate: [navGuard('/enrollments')],
        loadComponent: () =>
          import('./features/enrollments/center/enrollment-center').then((m) => m.EnrollmentCenterPage),
        data: { title: 'Matrículas' },
      },

      {
        path: 'teachers',
        canActivate: [navGuard('/teachers')],
        loadComponent: () => import('./features/catalog/teachers/teachers').then((m) => m.TeachersPage),
        data: { title: 'Docentes' },
      },
      {
        path: 'students',
        canActivate: [navGuard('/students')],
        loadComponent: () => import('./features/catalog/students/students').then((m) => m.StudentsPage),
        data: { title: 'Estudiantes' },
      },
      {
        path: 'rooms',
        canActivate: [navGuard('/rooms')],
        loadComponent: () => import('./features/catalog/rooms/rooms').then((m) => m.RoomsPage),
        data: { title: 'Aulas' },
      },
      {
        path: 'devices',
        canActivate: [navGuard('/devices')],
        loadComponent: () => import('./features/catalog/devices/devices').then((m) => m.DevicesPage),
        data: { title: 'Dispositivos' },
      },

      {
        path: 'calendar/holidays',
        canActivate: [navGuard('/calendar/holidays')],
        loadComponent: () =>
          import('./features/calendar/holidays/holidays.page').then((m) => m.HolidaysPage),
        data: { title: 'Feriados' },
      },
      {
        path: 'calendar/justifications',
        canActivate: [navGuard('/calendar/justifications')],
        loadComponent: () =>
          import('./features/calendar/justifications/justifications.page').then(
            (m) => m.JustificationsPage,
          ),
        data: { title: 'Justificaciones' },
      },
      {
        path: 'calendar/settings',
        canActivate: [navGuard('/calendar/settings')],
        loadComponent: () =>
          import('./features/calendar/settings/settings.page').then((m) => m.SettingsPage),
        data: { title: 'Parámetros del sistema' },
      },

      {
        path: 'faces',
        canActivate: [navGuard('/faces')],
        loadComponent: () =>
          import('./features/faces/faces-page/faces-page').then((m) => m.FacesPage),
        data: { title: 'Enrolamiento facial' },
      },
      {
        path: 'imports',
        canActivate: [navGuard('/imports')],
        loadComponent: () =>
          import('./features/imports/schedule-import/schedule-import').then(
            (m) => m.ScheduleImportPage,
          ),
        data: { title: 'Importar horario' },
      },
      {
        path: 'reports',
        canActivate: [navGuard('/reports')],
        loadComponent: () => import('./features/reports/reports').then((m) => m.ReportsPage),
        data: { title: 'Reportes' },
      },
      {
        path: 'audit',
        canActivate: [navGuard('/audit')],
        loadComponent: () => import('./features/audit/audit').then((m) => m.AuditPage),
        data: { title: 'Bitácora' },
      },
      {
        path: 'pilot',
        canActivate: [navGuard('/pilot')],
        loadComponent: () => import('./features/pilot/pilot').then((m) => m.PilotPage),
        data: { title: 'Prueba piloto' },
      },
    ],
  },
  {
    path: '**',
    loadComponent: () => import('./features/not-found/not-found').then((m) => m.NotFoundPage),
  },
];
