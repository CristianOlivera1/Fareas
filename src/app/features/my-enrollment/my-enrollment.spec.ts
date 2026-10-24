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
    mine: false, current_group_code: null, conflict: null, ...overrides,
  };
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

  async function load(open: boolean, offer: OfferGroup[], cycle: number | null = 5) {
    const page = TestBed.createComponent(MyEnrollmentPage).componentInstance;
    http.expectOne(`${API}/me/enrollment`).flush(status(open, cycle));
    http.expectOne((req) => req.url === `${API}/me/enrollment/offer`).flush(offer);
    await Promise.resolve();
    await Promise.resolve();
    await Promise.resolve();
    return page;
  }

  it('opens on the student cycle and lists the courses of that cycle', async () => {
    const page = await load(true, [
      group({ group_id: 1 }),
      group({ group_id: 2, course_id: 2, course_code: 'AIS61', cycle: 6 }),
    ]);

    expect(page.cycle()).toBe(5);
    expect(page.cycles()).toEqual([5, 6]);
    expect(page.courses().map((course) => course.code)).toEqual(['AIS51']);
    expect(page.open()).toBe(true);
  });

  it('classifies each group as mine, full, conflicting, switchable or free', async () => {
    const page = await load(true, [
      group({ group_id: 1, mine: true }),
      group({ group_id: 2, course_id: 2, full: true, free: 0 }),
      group({ group_id: 3, course_id: 3, conflict: 'AIS51 (grupo A)' }),
      group({ group_id: 4, course_id: 4, current_group_code: 'B' }),
      group({ group_id: 5, course_id: 5 }),
    ]);

    expect(page.offer().map((item) => page.stateOf(item))).toEqual(['mine', 'full', 'conflict', 'switch', 'free']);
  });

  it('builds the weekly schedule only from the enrolled groups', async () => {
    const page = await load(true, [group({ group_id: 1, mine: true }), group({ group_id: 2, course_id: 2 })]);

    expect(page.entries()).toHaveLength(1);
    expect(page.entries()[0]).toMatchObject({ course_code: 'AIS51', weekday: 1, room_code: 'LAB 305' });
  });

  it('computes the group letters of the cycle with their coverage', async () => {
    const page = await load(true, [
      group({ group_id: 1, group_code: 'A' }),
      group({ group_id: 2, course_id: 2, group_code: 'A' }),
      group({ group_id: 3, course_id: 2, group_code: 'B' }),
    ]);

    expect(page.letters()).toEqual([
      { letter: 'A', covered: 2, total: 2 },
      { letter: 'B', covered: 1, total: 2 },
    ]);
  });

  it('filters the courses by text', async () => {
    const page = await load(true, [
      group({ group_id: 1 }),
      group({ group_id: 2, course_id: 2, course_code: 'AIS52', course_name: 'Incubadoras de empresas' }),
    ]);

    page.query.set('incub');
    expect(page.courses().map((course) => course.code)).toEqual(['AIS52']);
  });

  it('enrolls in a group and reloads the offer', async () => {
    const page = await load(true, [group({ group_id: 7 })]);

    const enrolling = page.enroll(page.offer()[0]);
    const request = http.expectOne(`${API}/me/enrollment`);
    expect(request.request.body).toEqual({ group_id: 7 });
    request.flush({ message: 'ok' });
    await Promise.resolve();
    await Promise.resolve();
    http.expectOne(`${API}/me/enrollment`).flush(status(true));
    http.expectOne((req) => req.url === `${API}/me/enrollment/offer`).flush([group({ group_id: 7, mine: true })]);
    await enrolling;
    await Promise.resolve();

    expect(page.mine()).toHaveLength(1);
  });

  it('switches groups using the current group of the same course', async () => {
    const page = await load(true, [
      group({ group_id: 1, group_code: 'A', mine: true }),
      group({ group_id: 2, group_code: 'B', current_group_code: 'A' }),
    ]);

    const switching = page.switchTo(page.offer()[1]);
    const request = http.expectOne(`${API}/me/enrollment/1/transfer`);
    expect(request.request.body).toEqual({ destino_group_id: 2 });
    request.flush({ student_id: 1 });
    await Promise.resolve();
    await Promise.resolve();
    http.expectOne(`${API}/me/enrollment`).flush(status(true));
    http.expectOne((req) => req.url === `${API}/me/enrollment/offer`).flush([]);
    await switching;
  });

  it('asks for confirmation before withdrawing', async () => {
    const page = await load(true, [group({ group_id: 1, mine: true })]);

    page.askWithdraw(page.offer()[0]);
    expect(page.confirmingWithdraw()).toBe(1);
    page.cancelWithdraw();
    expect(page.confirmingWithdraw()).toBeNull();
  });

  it('knows when the window is closed', async () => {
    const page = await load(false, [group({ group_id: 1 })]);

    expect(page.open()).toBe(false);
    expect(page.status()?.window.message).toContain('cerró');
  });
});
