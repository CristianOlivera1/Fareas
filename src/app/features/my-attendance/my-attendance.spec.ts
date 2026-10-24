import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { MyAttendance, MyDpi } from '../../core/services/attendance-api';
import { MyAttendancePage } from './my-attendance';

const RECORD: MyAttendance = {
  record_id: 1,
  session_id: 10,
  session_date: '2026-10-20',
  start_time: '07:00',
  end_time: '09:00',
  course_id: 3,
  course_code: 'ISA901',
  course_name: 'Seguridad',
  group_code: 'A',
  status: 'falta',
  is_justified: true,
  marked_at: null,
  method: 'manual',
  correct_reason: null,
};

const DPI: MyDpi = {
  course_id: 3,
  course_code: 'ISA901',
  course_name: 'Seguridad',
  sessions_held: 10,
  absences: 3,
  justified_absences: 1,
  lates: 0,
  absence_percent: 30,
  nivel: 'alerta',
  sesiones_planificadas: 32,
  faltas_permitidas: 10,
  faltas_restantes: 7,
  semester_label: '2026-II',
};

describe('MyAttendancePage', () => {
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  function flushInitialLoad(page: MyAttendancePage) {
    http.expectOne((req) => req.url.endsWith('/attendance/me')).flush([RECORD]);
    http.expectOne((req) => req.url.endsWith('/attendance/me/dpi')).flush([DPI]);
    expect(page.loading()).toBe(false);
  }

  it('loads the history and the DPI summary', () => {
    const page = TestBed.createComponent(MyAttendancePage).componentInstance;
    flushInitialLoad(page);
    expect(page.records()).toEqual([RECORD]);
    expect(page.dpi()).toEqual([DPI]);
  });

  it('labels a justified absence and styles the DPI level', () => {
    const page = TestBed.createComponent(MyAttendancePage).componentInstance;
    flushInitialLoad(page);
    expect(page.label(RECORD)).toBe('Falta justificada');
    expect(page.severity(RECORD)).toBe('info');
    expect(page.style(DPI).label).toBe('En riesgo');
  });

  it('sends the date range when filtering', () => {
    const page = TestBed.createComponent(MyAttendancePage).componentInstance;
    flushInitialLoad(page);
    page.setFrom('2026-10-01');
    const request = http.expectOne((req) => req.url.endsWith('/attendance/me'));
    expect(request.request.params.get('desde')).toBe('2026-10-01');
    request.flush([]);
    http.expectOne((req) => req.url.endsWith('/attendance/me/dpi')).flush([]);
    expect(page.hasFilters()).toBe(true);
  });
});
