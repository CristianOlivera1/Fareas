import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { MessageService } from 'primeng/api';

import { AuthService } from '../../core/services/auth/auth';
import { ReportsPage } from './reports';

const API = 'http://localhost:8000/api/v1';

const CATALOG = [
  {
    key: 'attendance',
    title: 'Asistencia detallada',
    description: 'Un registro por alumno y sesión.',
    icon: 'material-symbols:table-chart-outline',
    formats: ['pdf', 'xlsx', 'csv'],
    filters: ['periodo', 'ciclo', 'curso', 'grupo', 'docente', 'aula', 'estado', 'alumno'],
  },
  {
    key: 'dpi-risk',
    title: 'Riesgo de inasistencia',
    description: 'Alumnos en riesgo.',
    icon: 'material-symbols:warning-outline',
    formats: ['pdf', 'xlsx', 'csv'],
    filters: ['ciclo', 'curso', 'alumno'],
  },
];

const PREVIEW = {
  key: 'attendance',
  title: 'Asistencia detallada',
  description: '',
  filters: [],
  indicators: [{ label: 'Registros', value: '2', tone: 'muted' }],
  columns: [{ key: 'a', title: 'Estudiante', align: 'left' }],
  rows: [[{ value: 'Ana', tone: null }]],
  total: 2,
  truncated: false,
};

describe('ReportsPage', () => {
  let fixture: ComponentFixture<ReportsPage>;
  let component: ReportsPage;
  let httpMock: HttpTestingController;

  async function settle(): Promise<void> {
    for (let i = 0; i < 6; i += 1) await Promise.resolve();
  }

  async function createPage(role: 'admin' | 'docente'): Promise<void> {
    await TestBed.configureTestingModule({
      imports: [ReportsPage],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        MessageService,
        { provide: AuthService, useValue: { currentUser: () => ({ id: 5, role }) } },
      ],
    }).compileComponents();
    fixture = TestBed.createComponent(ReportsPage);
    component = fixture.componentInstance;
    httpMock = TestBed.inject(HttpTestingController);
    fixture.detectChanges();

    httpMock.expectOne(`${API}/reports/catalog`).flush(CATALOG);
    httpMock.expectOne(`${API}/settings`).flush({ semester_start: '2026-08-10', semester_end: '2026-12-20' });
    httpMock.expectOne(`${API}/courses?page_size=100`).flush({ items: [], total: 0, page: 1, page_size: 100 });
    httpMock.expectOne(`${API}/groups`).flush([]);
    if (role === 'admin') {
      httpMock.expectOne(`${API}/teachers?page_size=100`).flush({ items: [], total: 0, page: 1, page_size: 100 });
    }
    httpMock.expectOne(`${API}/rooms?page_size=100`).flush({ items: [], total: 0, page: 1, page_size: 100 });
    await settle();
  }

  beforeEach(() => vi.useFakeTimers());

  afterEach(() => {
    vi.useRealTimers();
    httpMock.verify();
  });

  it('loads the preview of the selected report with the period and filters', async () => {
    await createPage('admin');
    component.cycle.set(4);
    component.toggleStatus('falta');
    component.search.set(' quispe ');
    fixture.detectChanges();
    await vi.advanceTimersByTimeAsync(400);

    const request = httpMock.expectOne((req) => req.url === `${API}/reports/preview`);
    expect(request.request.params.get('kind')).toBe('attendance');
    expect(request.request.params.get('cycle')).toBe('4');
    expect(request.request.params.get('status')).toBe('falta');
    expect(request.request.params.get('q')).toBe('quispe');
    expect(request.request.params.has('desde')).toBe(true);
    request.flush(PREVIEW);
    await settle();

    expect(component.preview()?.total).toBe(2);
    expect(component.activeFilters()).toBe(3);
  });

  it('only sends the filters the selected report supports', async () => {
    await createPage('admin');
    component.cycle.set(4);
    component.roomId.set(9);
    component.select('dpi-risk');
    fixture.detectChanges();
    await vi.advanceTimersByTimeAsync(400);

    const request = httpMock.expectOne((req) => req.url === `${API}/reports/preview`);
    expect(request.request.params.get('kind')).toBe('dpi-risk');
    expect(request.request.params.get('cycle')).toBe('4');
    expect(request.request.params.has('room_id')).toBe(false);
    expect(request.request.params.has('desde')).toBe(false);
    request.flush({ ...PREVIEW, key: 'dpi-risk' });
  });

  it('downloads the chosen format with the same query', async () => {
    await createPage('admin');
    component.format.set('csv');
    component.onCycle(2);

    const downloading = component.download();
    const request = httpMock.expectOne((req) => req.url === `${API}/reports/export`);
    expect(request.request.params.get('format')).toBe('csv');
    expect(request.request.params.get('kind')).toBe('attendance');
    expect(request.request.params.get('cycle')).toBe('2');
    URL.createObjectURL = () => 'blob:test';
    request.flush(new Blob(['x']), { headers: { 'Content-Disposition': 'attachment; filename="r.csv"' } });
    await downloading;
    await vi.advanceTimersByTimeAsync(400);
    httpMock.match((req) => req.url === `${API}/reports/preview`).forEach((r) => r.flush(PREVIEW));

    expect(component.downloading()).toBe(false);
  });

  it('hides the teacher filter for teachers and flags an invalid range', async () => {
    await createPage('docente');

    expect(component.isTeacher()).toBe(true);
    expect(component.query().teacher_id).toBeNull();
    component.onDate('from', '2026-12-01');
    component.onDate('to', '2026-11-01');

    expect(component.rangeError()).toContain('no puede ser posterior');
    expect(component.canDownload()).toBe(false);
    httpMock.match((req) => req.url === `${API}/reports/preview`);
  });

  it('applies period presets and marks custom edits', async () => {
    await createPage('admin');
    component.applyPreset('semester');

    expect(component.from()).toBe('2026-08-10');
    component.onDate('to', '2026-09-01');
    expect(component.preset()).toBe('custom');
    httpMock.match((req) => req.url === `${API}/reports/preview`);
  });
});
