import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';

import { PilotPage } from './pilot';

const API = 'http://localhost:8000/api/v1';

const RATE_EMPTY = { count: 0, total: 0, value: null, low: null, high: null };

const STATUS = {
  camera_room: 'LAB 104',
  students: [
    { id: 4, code: '221181', name: 'Ana Quispe', alias: 'P01', normal: 3, adversa: 1 },
    { id: 9, code: '221190', name: 'Luis Mamani', alias: 'P02', normal: 0, adversa: 0 },
  ],
  captures: 4,
  unenrolled_captures: 0,
  tar: { count: 3, total: 4, value: 0.75, low: 0.3, high: 0.95 },
  frr: RATE_EMPTY,
  misidentified: RATE_EMPTY,
  far: RATE_EMPTY,
  curve: [],
};

describe('PilotPage', () => {
  let fixture: ComponentFixture<PilotPage>;
  let component: PilotPage;
  let httpMock: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [PilotPage],
      providers: [provideHttpClient(), provideHttpClientTesting()],
    }).compileComponents();
    fixture = TestBed.createComponent(PilotPage);
    component = fixture.componentInstance;
    httpMock = TestBed.inject(HttpTestingController);
    fixture.detectChanges();
    httpMock.expectOne((req) => req.url === `${API}/pilot/status`).flush(STATUS);
    fixture.detectChanges();
  });

  afterEach(() => httpMock.verify());

  it('lists the enrolled students with their capture progress', () => {
    expect(component.studentOptions().map((option) => option.value)).toEqual([4, 9]);
    expect(component.pending()).toBe(2);
    expect(fixture.nativeElement.textContent).toContain('Ana Quispe');
  });

  it('only allows capturing once a student or a non-enrolled person is chosen', () => {
    expect(component.canCapture()).toBe(false);

    component.studentId.set(4);
    expect(component.canCapture()).toBe(true);

    component.studentId.set(null);
    component.toggleUnenrolled(true);
    expect(component.canCapture()).toBe(true);
  });

  it('sends the capture and refreshes the results', () => {
    component.studentId.set(4);
    component.condition.set('adversa');
    component.capture();

    const request = httpMock.expectOne(`${API}/pilot/captures`);
    expect(request.request.body).toEqual({ student_id: 4, condition: 'adversa', seconds: 10 });
    request.flush({ capture_id: 'abc', frames: 12, alias: 'P01', condition: 'adversa' });

    expect(component.message()).toContain('12 cuadros');
    httpMock.expectOne((req) => req.url === `${API}/pilot/status`).flush(STATUS);
  });

  it('recomputes the results when the threshold changes', () => {
    component.setNumber('threshold', '0.6');

    const request = httpMock.expectOne((req) => req.url === `${API}/pilot/status`);
    expect(request.request.params.get('threshold')).toBe('0.6');
    request.flush(STATUS);
  });

  it('formats rates with their confidence interval', () => {
    expect(component.percent(0.75)).toBe('75.0 %');
    expect(component.interval(STATUS.tar)).toContain('IC 95 %');
    expect(component.interval(RATE_EMPTY)).toBe('sin datos');
  });
});
