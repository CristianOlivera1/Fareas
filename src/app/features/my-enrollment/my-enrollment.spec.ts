import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { MessageService } from 'primeng/api';

import { EnrollmentStatus, OfferGroup } from '../../core/models/enrollment';
import { MyEnrollmentPage } from './my-enrollment';

const API = 'http://localhost:8000/api/v1';

function group(overrides: Partial<OfferGroup>): OfferGroup {
  return {
    group_id: 1, course_id: 1, course_code: 'AIS51', course_name: 'Cálculo integral', cycle: 5, group_code: 'A',
    teacher_name: 'Docente', capacity: 40, enrolled: 10, free: 30, full: false,
    blocks: [{ weekday: 1, start_time: '08:00', end_time: '10:00', room_code: 'LAB 305' }],
    mine: false, current_group_code: null, conflict: null, will_create_group: false, ...overrides,
  };
}

function pending(overrides: Partial<OfferGroup>): OfferGroup {
  return group({ group_id: null, blocks: [], teacher_name: null, will_create_group: true, free: 40, enrolled: 0, ...overrides });
}

function status(open: boolean, cycle: number | null = 5): EnrollmentStatus {
  return {
    period: '2026-II', student_cycle: cycle, enrolled_groups: 1,
    window: { open, start: '2026-10-20', end: '2026-10-30', message: open ? 'Matrícula abierta hasta el 30/10/2026.' : 'La matrícula cerró el 30/10/2026.' },
  };
}

describe('MyEnrollmentPage', () => {
  let http: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [MyEnrollmentPage],
      providers: [provideHttpClient(), provideHttpClientTesting(), MessageService],
    }).compileComponents();
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  async function flush() {
    for (let i = 0; i < 4; i += 1) await Promise.resolve();
  }

  async function load(open: boolean, offer: OfferGroup[], cycle: number | null = 5) {
    const page = TestBed.createComponent(MyEnrollmentPage).componentInstance;
    http.expectOne(`${API}/me/enrollment`).flush(status(open, cycle));
    http.expectOne((req) => req.url === `${API}/me/enrollment/offer`).flush(offer);
    await flush();
    return page;
  }

  it('opens on the student cycle and groups the groups of each course', async () => {
    const page = await load(true, [
      group({ group_id: 1 }),
      group({ group_id: 2, group_code: 'B' }),
      group({ group_id: 3, course_id: 2, course_code: 'AIS61', cycle: 6 }),
    ]);

    expect(page.cycle()).toBe(5);
    expect(page.cycles()).toEqual([5, 6]);
    expect(page.courses().map((course) => [course.code, course.groups.length])).toEqual([['AIS51', 2]]);
  });

  it('shows the courses without group as pending and lets them be selected', async () => {
    const page = await load(true, [pending({ course_id: 9, course_code: 'AIS59' })]);

    const [course] = page.courses();
    expect(course.pending).toBe(true);
    expect(page.blockedReason(course)).toBeNull();
    page.toggle(course);
    expect(page.selectedIds()).toEqual([9]);
    expect(page.canConfirm()).toBe(true);
  });

  it('keeps the selection when the cycle changes and counts it per cycle', async () => {
    const page = await load(true, [
      group({ group_id: 1 }),
      group({ group_id: 3, course_id: 2, course_code: 'AIS61', cycle: 6, blocks: [{ weekday: 2, start_time: '08:00', end_time: '10:00', room_code: null }] }),
    ]);

    page.toggle(page.courses()[0]);
    page.setCycle(6);
    page.toggle(page.courses()[0]);

    expect(page.selectedIds().sort()).toEqual([1, 2]);
    expect(page.selectedInCycle(5)).toBe(1);
    expect(page.selectedInCycle(6)).toBe(1);
  });

  it('requires choosing a group when the course has several and blocks the confirmation until then', async () => {
    const page = await load(true, [group({ group_id: 1 }), group({ group_id: 2, group_code: 'B' })]);

    page.toggle(page.courses()[0]);
    expect(page.missingChoices()).toHaveLength(1);
    expect(page.canConfirm()).toBe(false);

    page.chooseGroup(page.courses()[0], 2);
    expect(page.missingChoices()).toHaveLength(0);
    expect(page.canConfirm()).toBe(true);
  });

  it('warns about overlaps between the selected courses', async () => {
    const page = await load(true, [
      group({ group_id: 1 }),
      group({ group_id: 2, course_id: 2, course_code: 'AIS52', blocks: [{ weekday: 1, start_time: '09:00', end_time: '11:00', room_code: null }] }),
    ]);

    page.courses().forEach((course) => page.toggle(course));

    expect(page.selectionConflicts().get(1)).toBe('AIS52');
    expect(page.selectionConflicts().get(2)).toBe('AIS51');
    expect(page.canConfirm()).toBe(false);
  });

  it('does not let a full or conflicting course be selected', async () => {
    const page = await load(true, [
      group({ group_id: 1, full: true, free: 0 }),
      group({ group_id: 2, course_id: 2, course_code: 'AIS52', conflict: 'AIS11 (grupo A)' }),
    ]);

    const [full, conflicting] = page.courses();
    expect(page.blockedReason(full)).toBe('Cupo lleno');
    expect(page.blockedReason(conflicting)).toContain('AIS11');
    page.toggle(full);
    page.toggle(conflicting);
    expect(page.selectedIds()).toEqual([]);
  });

  it('confirms the selection in one request and keeps only the failures selected', async () => {
    const page = await load(true, [
      group({ group_id: 1 }),
      group({ group_id: 2, course_id: 2, course_code: 'AIS52', blocks: [{ weekday: 3, start_time: '08:00', end_time: '10:00', room_code: null }] }),
      pending({ course_id: 3, course_code: 'AIS53' }),
    ]);
    page.courses().forEach((course) => page.toggle(course));

    const confirming = page.confirm();
    const request = http.expectOne(`${API}/me/enrollment/bulk`);
    expect(request.request.body).toEqual({
      items: [
        { course_id: 1, group_id: 1 },
        { course_id: 2, group_id: 2 },
        { course_id: 3, group_id: null },
      ],
    });
    request.flush({
      ok: 2, skipped: 0, failed: 1,
      results: [
        { course_id: 1, course_code: 'AIS51', group_id: 1, group_code: 'A', status: 'ok', reason: null },
        { course_id: 2, course_code: 'AIS52', group_id: 2, group_code: 'A', status: 'failed', reason: 'Grupo lleno (40/40)' },
        { course_id: 3, course_code: 'AIS53', group_id: 11, group_code: 'A', status: 'ok', reason: null },
      ],
    });
    await flush();
    http.expectOne(`${API}/me/enrollment`).flush(status(true));
    http.expectOne((req) => req.url === `${API}/me/enrollment/offer`).flush([]);
    await confirming;
    await flush();

    expect(page.selectedIds()).toEqual([2]);
    expect(page.failureOf(2)).toBe('Grupo lleno (40/40)');
  });

  it('does not allow selecting anything when the window is closed', async () => {
    const page = await load(false, [group({ group_id: 1 })]);

    page.toggle(page.courses()[0]);

    expect(page.open()).toBe(false);
    expect(page.selectedIds()).toEqual([]);
  });

  it('switches groups from the enrolled course and asks before withdrawing', async () => {
    const page = await load(true, [
      group({ group_id: 1, group_code: 'A', mine: true }),
      group({ group_id: 2, group_code: 'B', current_group_code: 'A' }),
    ]);
    const [course] = page.courses();

    expect(course.current?.group_id).toBe(1);
    page.askWithdraw(course);
    expect(page.confirmingWithdraw()).toBe(course.courseId);
    page.cancelWithdraw();
    expect(page.confirmingWithdraw()).toBeNull();

    const switching = page.switchTo(course, course.groups[1]);
    const request = http.expectOne(`${API}/me/enrollment/1/transfer`);
    expect(request.request.body).toEqual({ destino_group_id: 2 });
    request.flush({ student_id: 1 });
    await flush();
    http.expectOne(`${API}/me/enrollment`).flush(status(true));
    http.expectOne((req) => req.url === `${API}/me/enrollment/offer`).flush([]);
    await switching;
  });
});
