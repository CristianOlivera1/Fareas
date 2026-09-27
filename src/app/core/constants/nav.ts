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

export const NAV: readonly NavEntry[] = [
  { label: 'Dashboard', route: '/dashboard', icon: 'material-symbols:dashboard-outline', roles: TODOS },
  { label: 'Asistencias', route: '/attendance', icon: 'material-symbols:fact-check-outline', roles: TODOS },
  {
    label: 'Académico',
    icon: 'material-symbols:menu-book-outline',
    roles: TODOS,
    children: [
      { label: 'Cursos y grupos', route: '/courses', icon: 'material-symbols:auto-stories-outline', roles: TODOS },
      { label: 'Matrículas', route: '/enrollments', icon: 'material-symbols:how-to-reg-outline', roles: TODOS },
    ],
  },
  {
    label: 'Catálogo',
    icon: 'material-symbols:category-outline',
    roles: TODOS,
    children: [
      { label: 'Docentes', route: '/teachers', icon: 'material-symbols:person-outline', roles: SOLO_ADMIN },
      { label: 'Estudiantes', route: '/students', icon: 'material-symbols:school-outline', roles: TODOS },
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
      { label: 'Reportes', route: '/reports', icon: 'material-symbols:description-outline', roles: TODOS },
      { label: 'Bitácora', route: '/audit', icon: 'material-symbols:history-toggle-off-outline', roles: SOLO_ADMIN },
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
