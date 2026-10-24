import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ScheduleRow } from '../../core/models/catalog';
import { AuthService } from '../../core/services/auth/auth';
import { MyDpi } from '../../core/services/attendance-api';
import { StudentHomePage } from './student-home';

function row(id: number, weekday: number, start: string, end: string): ScheduleRow {
  return {
    id,
    group_id: id,
    course_id: id,
    course_code: `ISA90${id}`,
    course_name: `Curso ${id}`,
    group_code: 'A',
    teacher_id: 1,
    teacher_name: 'Docente',
    room_id: 1,
    room_code: 'LAB 305',
    semester_label: '2026-II',
    cycle: 9,
    weekday,
    start_time: start,
    end_time: end,
  };
}

function dpi(courseId: number, percent: number, nivel: MyDpi['nivel']): MyDpi {
  return {
    course_id: courseId,
    course_code: `ISA90${courseId}`,
    course_name: `Curso ${courseId}`,
    sessions_held: 10,
    absences: 2,
    justified_absences: 0,
    lates: 0,
    absence_percent: percent,
    nivel,
    sesiones_planificadas: 32,
    faltas_permitidas: 10,
    faltas_restantes: 8,
    semester_label: '2026-II',
  };
}

describe('StudentHomePage', () => {
  let http: HttpTestingController;

  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(2026, 9, 21, 9, 30));
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([]),
        { provide: AuthService, useValue: { currentUser: () => ({ full_name: 'Raul Montesinos' }) } },
      ],
    });
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  function load(schedule: ScheduleRow[], items: MyDpi[]): StudentHomePage {
    const page = TestBed.createComponent(StudentHomePage).componentInstance;
    http.expectOne((req) => req.url.endsWith('/me/schedule')).flush(schedule);
    http.expectOne((req) => req.url.endsWith('/attendance/me/dpi')).flush(items);
    http.expectOne((req) => req.url.endsWith('/attendance/me')).flush([]);
    return page;
  }

  it('keeps only today\'s classes and marks done, current and upcoming ones', () => {
    const page = load(
      [
        row(1, 3, '07:00:00', '09:00:00'),
        row(2, 3, '09:00:00', '11:00:00'),
        row(3, 3, '14:00:00', '16:00:00'),
        row(4, 4, '07:00:00', '09:00:00'),
      ],
      [],
    );
    expect(page.todayClasses().map((item) => [item.row.id, item.state])).toEqual([
      [1, 'done'],
      [2, 'now'],
      [3, 'next'],
    ]);
  });

  it('lists only courses with a risk level, worst first', () => {
    const page = load([], [dpi(1, 5, null), dpi(2, 24, 'alerta'), dpi(3, 41, 'limite')]);
    expect(page.atRisk().map((item) => item.course_id)).toEqual([3, 2]);
  });

  it('greets the student by first name', () => {
    const page = load([], []);
    expect(page.firstName()).toBe('Raul');
  });
});
