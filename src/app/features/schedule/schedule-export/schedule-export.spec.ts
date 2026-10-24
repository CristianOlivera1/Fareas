import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { MessageService } from 'primeng/api';

import { ScheduleExport } from './schedule-export';

const API = 'http://localhost:8000/api/v1';

describe('ScheduleExport', () => {
  let fixture: ComponentFixture<ScheduleExport>;
  let component: ScheduleExport;
  let httpMock: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [ScheduleExport],
      providers: [provideHttpClient(), provideHttpClientTesting(), MessageService],
    }).compileComponents();
    fixture = TestBed.createComponent(ScheduleExport);
    component = fixture.componentInstance;
    httpMock = TestBed.inject(HttpTestingController);
    fixture.componentRef.setInput('semesters', ['2026-II', '2026-I']);
    fixture.componentRef.setInput('semester', '2026-II');
    fixture.componentRef.setInput('cycle', 4);
    fixture.componentRef.setInput('filters', { courseId: 0, teacherId: 5, roomId: 0 });
    fixture.componentInstance.visible.set(true);
    fixture.detectChanges();
  });

  afterEach(() => httpMock.verify());

  it('starts from the page context', () => {
    expect(component.chosenSemester()).toBe('2026-II');
    expect(component.chosenCycle()).toBe(4);
    expect(component.useFilters()).toBe(true);
  });

  it('requests the chosen format with the options and filters', async () => {
    component.format.set('xlsx');
    component.chosenSemester.set('2026-I');
    component.chosenCycle.set(0);
    component.showRoom.set(false);

    const exporting = component.export();
    const request = httpMock.expectOne((req) => req.url === `${API}/schedule/export`);
    expect(request.request.params.get('format')).toBe('xlsx');
    expect(request.request.params.get('semester')).toBe('2026-I');
    expect(request.request.params.has('cycle')).toBe(false);
    expect(request.request.params.get('teacher_id')).toBe('5');
    expect(request.request.params.get('show_room')).toBe('false');
    request.flush(new Blob(['x']), {
      headers: { 'Content-Disposition': 'attachment; filename="horario.xlsx"' },
    });
    URL.createObjectURL = () => 'blob:test';
    await exporting;

    expect(component.visible()).toBe(false);
  });

  it('warns that several cycles as PNG are zipped', () => {
    component.format.set('png');
    component.chosenCycle.set(0);

    expect(component.note()).toContain('ZIP');
  });
});
