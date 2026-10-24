import { signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { ActivatedRouteSnapshot, Router, RouterStateSnapshot, UrlTree } from '@angular/router';
import { MessageService } from 'primeng/api';

import { navForRole, ROLE_HOME, rolesForRoute } from '../constants/nav';
import type { SessionUser, UserRole } from '../models/user';
import { AuthService } from '../services/auth/auth';
import { authGuard, loginGuard, mustChangePasswordGuard, navGuard } from './auth-guard';

function sessionFor(role: UserRole, mustChange = false): SessionUser {
  return { id: 1, full_name: 'Test', email: 't@unamba.edu.pe', role, must_change_password: mustChange };
}

describe('role guards', () => {
  const user = signal<SessionUser | null>(null);
  const toast = { add: vi.fn() };

  const run = (guard: ReturnType<typeof navGuard>) =>
    TestBed.runInInjectionContext(() =>
      guard({} as ActivatedRouteSnapshot, {} as RouterStateSnapshot),
    );

  const urlOf = (result: unknown): string => TestBed.inject(Router).serializeUrl(result as UrlTree);

  beforeEach(() => {
    user.set(null);
    toast.add.mockClear();
    TestBed.configureTestingModule({
      providers: [
        { provide: MessageService, useValue: toast },
        {
          provide: AuthService,
          useValue: {
            currentUser: user,
            isAuthenticated: () => user() !== null,
            mustChangePassword: () => user()?.must_change_password ?? false,
          },
        },
      ],
    });
  });

  it('authGuard sends anonymous users to login', () => {
    expect(urlOf(run(authGuard))).toBe('/login');
  });

  it('authGuard forces the password change', () => {
    user.set(sessionFor('docente', true));
    expect(urlOf(run(authGuard))).toBe('/auth/change-password');
  });

  it('loginGuard redirects each role to its home', () => {
    for (const role of ['admin', 'docente', 'estudiante'] as UserRole[]) {
      user.set(sessionFor(role));
      expect(urlOf(run(loginGuard))).toBe(ROLE_HOME[role]);
    }
  });

  it('mustChangePasswordGuard redirects to the role home once changed', () => {
    user.set(sessionFor('estudiante'));
    expect(urlOf(run(mustChangePasswordGuard))).toBe(ROLE_HOME.estudiante);
  });

  it('navGuard blocks a student from the dashboard and warns', () => {
    user.set(sessionFor('estudiante'));
    expect(urlOf(run(navGuard('/dashboard')))).toBe(ROLE_HOME.estudiante);
    expect(toast.add).toHaveBeenCalled();
  });

  it('navGuard blocks a teacher from admin-only routes', () => {
    user.set(sessionFor('docente'));
    expect(urlOf(run(navGuard('/teachers')))).toBe(ROLE_HOME.docente);
    expect(urlOf(run(navGuard('/courses')))).toBe(ROLE_HOME.docente);
  });

  it('navGuard lets teachers and students share the schedule route', () => {
    user.set(sessionFor('docente'));
    expect(run(navGuard('/my-schedule'))).toBe(true);
    user.set(sessionFor('estudiante'));
    expect(run(navGuard('/my-schedule'))).toBe(true);
    expect(urlOf(run(navGuard('/my-groups')))).toBe(ROLE_HOME.estudiante);
  });

  it('navGuard allows each role into its own routes', () => {
    user.set(sessionFor('admin'));
    expect(run(navGuard('/audit'))).toBe(true);
    user.set(sessionFor('docente'));
    expect(run(navGuard('/reports'))).toBe(true);
    user.set(sessionFor('estudiante'));
    expect(run(navGuard('/me'))).toBe(true);
  });
});

describe('navForRole', () => {
  const labels = (role: UserRole) => navForRole(role).map((entry) => entry.label);
  const childLabels = (role: UserRole, group: string) =>
    navForRole(role)
      .find((entry) => entry.label === group)
      ?.children?.map((child) => child.label);

  it('gives the student a personal menu', () => {
    expect(labels('estudiante')).toEqual([
      'Inicio',
      'Mi horario',
      'Mi matrícula',
      'Mis asistencias',
      'Mis justificaciones',
    ]);
  });

  it('gives the teacher a teaching menu without administration groups', () => {
    expect(labels('docente')).toEqual([
      'Dashboard',
      'Asistencias',
      'Mi docencia',
      'Calendario',
      'Herramientas',
    ]);
    expect(childLabels('docente', 'Mi docencia')).toEqual([
      'Mis grupos',
      'Mi horario',
      'Alumnos en riesgo',
    ]);
    expect(childLabels('docente', 'Herramientas')).toEqual(['Reportes']);
  });

  it('keeps every administration group for the admin', () => {
    expect(labels('admin')).toEqual([
      'Dashboard',
      'Asistencias',
      'Académico',
      'Catálogo',
      'Calendario',
      'Herramientas',
    ]);
    expect(childLabels('admin', 'Herramientas')).toContain('Alumnos en riesgo');
  });
});

describe('rolesForRoute', () => {
  it('merges the roles of entries that share a route', () => {
    expect([...rolesForRoute('/my-schedule')].sort()).toEqual(['docente', 'estudiante']);
    expect([...rolesForRoute('/at-risk')].sort()).toEqual(['admin', 'docente']);
  });

  it('returns no roles for unknown routes', () => {
    expect(rolesForRoute('/nowhere')).toEqual([]);
  });
});
