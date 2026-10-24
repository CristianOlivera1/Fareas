import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { MessageService } from 'primeng/api';

import { BulkResult, CyclePackage } from '../../../core/models/enrollment';
import { CycleEnrollment } from './cycle-enrollment';

const API = 'http://localhost:8000/api/v1';

const PACKAGE: CyclePackage = {
  period: '2026-II',
  cycle: 5,
  group_code: 'A',
  courses: [
    {
      course_id: 1, course_code: 'AIS51', course_name: 'Cálculo integral', group_id: 11, group_code: 'A',
      teacher_name: 'Docente Uno', capacity: 40, enrolled: 10, free: 30,
      blocks: [{ weekday: 1, start_time: '08:00', end_time: '10:00', room_code: 'LAB 305' }],
    },
    {
      course_id: 2, course_code: 'AIS52', course_name: 'Incubadoras', group_id: 12, group_code: 'A',
      teacher_name: null, capacity: 40, enrolled: 38, free: 2, blocks: [],
    },
  ],
  missing: [{ course_id: 3, course_code: 'AGG21', course_name: 'Estadística' }],
};

describe('CycleEnrollment', () => {
  let component: CycleEnrollment;
  let http: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [CycleEnrollment],
      providers: [provideHttpClient(), provideHttpClientTesting(), MessageService],
    }).compileComponents();
    component = TestBed.createComponent(CycleEnrollment).componentInstance;
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  async function pickPackage() {
    const picking = component.onCycle(5);
    http.expectOne((req) => req.url === `${API}/enrollment/package-letters` && req.params.get('cycle') === '5').flush([
      { group_code: 'A', courses_covered: 5, courses_total: 6 },
      { group_code: 'B', courses_covered: 6, courses_total: 6 },
    ]);
    await Promise.resolve();
    await Promise.resolve();
    const preview = http.expectOne((req) => req.url === `${API}/enrollment/package`);
    expect(preview.request.params.get('group_code')).toBe('B');
    preview.flush({ ...PACKAGE, group_code: 'B' });
    await picking;
  }

  it('selects the group that covers the most courses and loads its preview', async () => {
    await pickPackage();

    expect(component.letter()).toBe('B');
    expect(component.pkg()?.courses).toHaveLength(2);
    expect(component.minFree()).toBe(2);
  });

  it('merges students without duplicates and warns about tight seats', async () => {
    await pickPackage();
    component.add([
      { id: 1, code: '221181', full_name: 'Uno', semester: 5 },
      { id: 2, code: '221182', full_name: 'Dos', semester: 5 },
      { id: 3, code: '221183', full_name: 'Tres', semester: 5 },
    ]);
    component.add([{ id: 2, code: '221182', full_name: 'Dos', semester: 5 }]);

    expect(component.picked()).toHaveLength(3);
    expect(component.totalPairs()).toBe(6);
    expect(component.tightCourses().map((course) => course.course_code)).toEqual(['AIS52']);

    component.remove(1);
    expect(component.picked().map((student) => student.id)).toEqual([2, 3]);
  });

  it('resolves pasted codes into students and reports the unknown ones', async () => {
    component.pasted.set('221181, 221182\n999999 y texto');
    const resolving = component.resolveCodes();
    const request = http.expectOne(`${API}/enrollment/resolve-students`);
    expect(request.request.body).toEqual({ codes: ['221181', '221182', '999999'] });
    request.flush({
      found: [{ id: 1, code: '221181', full_name: 'Uno', semester: 5 }, { id: 2, code: '221182', full_name: 'Dos', semester: 5 }],
      unknown: ['999999'],
    });
    await resolving;

    expect(component.picked()).toHaveLength(2);
    expect(component.unknownCodes()).toEqual(['999999']);
    expect(component.pasted()).toBe('');
  });

  it('enrolls the selection in the package and groups the failures per student', async () => {
    await pickPackage();
    component.add([
      { id: 1, code: '221181', full_name: 'Uno', semester: 5 },
      { id: 2, code: '221182', full_name: 'Dos', semester: 5 },
    ]);

    const confirming = component.confirm();
    const request = http.expectOne(`${API}/enrollment/package`);
    expect(request.request.method).toBe('POST');
    expect(request.request.body).toEqual({ student_ids: [1, 2], cycle: 5, group_code: 'B' });
    const result: BulkResult = {
      students: 2, groups: 2, ok: 3, skipped: 0, failed: 1, unknown: [], missing: [],
      results: [
        { student_id: 2, student_code: '221182', student_name: 'Dos', group_id: 12, course_code: 'AIS52', group_code: 'B', status: 'failed', reason: 'Grupo lleno (40/40)' },
        { student_id: 2, student_code: '221182', student_name: 'Dos', group_id: 13, course_code: 'AIS53', group_code: 'B', status: 'failed', reason: 'El horario se cruza' },
      ],
    };
    request.flush(result);
    await Promise.resolve();
    await Promise.resolve();
    http.expectOne((req) => req.url === `${API}/enrollment/package` && req.method === 'GET').flush(PACKAGE);
    await confirming;

    expect(component.result()?.ok).toBe(3);
    expect(component.failures()).toEqual([
      { key: '2', name: '221182 · Dos', reasons: ['AIS52: Grupo lleno (40/40)', 'AIS53: El horario se cruza'] },
    ]);
    component.startOver();
    expect(component.picked()).toHaveLength(0);
  });

  it('does not allow confirming without students or without a package', () => {
    expect(component.canConfirm()).toBe(false);
    component.add([{ id: 1, code: '221181', full_name: 'Uno', semester: 5 }]);
    expect(component.canConfirm()).toBe(false);
  });
});
