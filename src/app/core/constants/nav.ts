import type { UserRole } from '../models/user';

export interface NavChild {
  readonly label: string;
  readonly route: string;
  readonly icon: string;
  readonly roles: UserRole[];
}

export interface NavGroup {
  readonly label: string;
  readonly icon: string;
  readonly roles: UserRole[];
  readonly children: NavChild[];
}

export type NavEntry = NavGroup | (NavChild & { children?: undefined });

const TODOS: UserRole[] = ['admin', 'docente'];
const SOLO_ADMIN: UserRole[] = ['admin'];
const SOLO_ESTUDIANTE: UserRole[] = ['estudiante'];
const SOLO_DOCENTE: UserRole[] = ['docente'];

export const ADMIN_PREFIX = '/admin';

export const ROLE_HOME: Record<UserRole, string> = {
  admin: `${ADMIN_PREFIX}/dashboard`,
  docente: `${ADMIN_PREFIX}/dashboard`,
  estudiante: `${ADMIN_PREFIX}/me`,
};

export const NAV: readonly NavEntry[] = [
  { label: 'Inicio', route: '/me', icon: 'material-symbols:home-outline', roles: SOLO_ESTUDIANTE },
  { label: 'Mi horario', route: '/my-schedule', icon: 'material-symbols:calendar-view-week', roles: SOLO_ESTUDIANTE },
  { label: 'Mi matrícula', route: '/my-enrollment', icon: 'material-symbols:how-to-reg-outline', roles: SOLO_ESTUDIANTE },
  { label: 'Mis asistencias', route: '/my-attendance', icon: 'material-symbols:fact-check-outline', roles: SOLO_ESTUDIANTE },
  { label: 'Mis justificaciones', route: '/my-justifications', icon: 'material-symbols:medical-information-outline', roles: SOLO_ESTUDIANTE },
  { label: 'Dashboard', route: '/dashboard', icon: 'material-symbols:dashboard-outline', roles: TODOS },
  { label: 'Asistencias', route: '/attendance', icon: 'material-symbols:fact-check-outline', roles: TODOS },
  {
    label: 'Mi docencia',
    icon: 'material-symbols:co-present-outline',
    roles: SOLO_DOCENTE,
    children: [
      { label: 'Mis grupos', route: '/my-groups', icon: 'material-symbols:groups-outline', roles: SOLO_DOCENTE },
      { label: 'Mi horario', route: '/my-schedule', icon: 'material-symbols:calendar-view-week', roles: SOLO_DOCENTE },
      { label: 'Alumnos en riesgo', route: '/at-risk', icon: 'material-symbols:warning-outline', roles: SOLO_DOCENTE },
    ],
  },
  {
    label: 'Académico',
    icon: 'material-symbols:menu-book-outline',
    roles: SOLO_ADMIN,
    children: [
      { label: 'Cursos y grupos', route: '/courses', icon: 'material-symbols:auto-stories-outline', roles: SOLO_ADMIN },
      { label: 'Horario general', route: '/schedule', icon: 'material-symbols:calendar-view-week', roles: SOLO_ADMIN },
      { label: 'Matrículas', route: '/enrollments', icon: 'material-symbols:how-to-reg-outline', roles: SOLO_ADMIN },
    ],
  },
  {
    label: 'Catálogo',
    icon: 'material-symbols:category-outline',
    roles: SOLO_ADMIN,
    children: [
      { label: 'Docentes', route: '/teachers', icon: 'material-symbols:person-outline', roles: SOLO_ADMIN },
      { label: 'Estudiantes', route: '/students', icon: 'material-symbols:school-outline', roles: SOLO_ADMIN },
      { label: 'Aulas', route: '/rooms', icon: 'material-symbols:meeting-room-outline', roles: SOLO_ADMIN },
      { label: 'Dispositivos', route: '/devices', icon: 'material-symbols:videocam-outline', roles: SOLO_ADMIN },
    ],
  },
  {
    label: 'Calendario',
    icon: 'material-symbols:calendar-month-outline',
    roles: TODOS,
    children: [
      { label: 'Feriados', route: '/calendar/holidays', icon: 'material-symbols:event-busy-outline', roles: TODOS },
      { label: 'Justificaciones', route: '/calendar/justifications', icon: 'material-symbols:medical-information-outline', roles: TODOS },
      { label: 'Parámetros', route: '/calendar/settings', icon: 'material-symbols:tune', roles: SOLO_ADMIN },
    ],
  },
  {
    label: 'Herramientas',
    icon: 'material-symbols:construction-outline',
    roles: TODOS,
    children: [
      { label: 'Enrolamiento facial', route: '/faces', icon: 'material-symbols:face-retouching-natural', roles: SOLO_ADMIN },
      { label: 'Importar horario', route: '/imports', icon: 'material-symbols:upload-file-outline', roles: SOLO_ADMIN },
      { label: 'Alumnos en riesgo', route: '/at-risk', icon: 'material-symbols:warning-outline', roles: SOLO_ADMIN },
      { label: 'Reportes', route: '/reports', icon: 'material-symbols:description-outline', roles: TODOS },
      { label: 'Bitácora', route: '/audit', icon: 'material-symbols:history-toggle-off-outline', roles: SOLO_ADMIN },
      { label: 'Prueba piloto', route: '/pilot', icon: 'material-symbols:science-outline', roles: SOLO_ADMIN },
    ],
  },
];

export function navForRole(role: UserRole | undefined): NavEntry[] {
  if (!role) return [];
  return NAV.filter((entry) => entry.roles.includes(role)).map((entry) =>
    'children' in entry && entry.children
      ? { ...entry, children: entry.children.filter((c) => c.roles.includes(role)) }
      : entry,
  );
}

export function rolesForRoute(route: string): UserRole[] {
  const roles = new Set<UserRole>();
  for (const entry of NAV) {
    const matches = entry.children
      ? entry.children.filter((child) => child.route === route)
      : entry.route === route
        ? [entry]
        : [];
    matches.forEach((match) => match.roles.forEach((role) => roles.add(role)));
  }
  return [...roles];
}
