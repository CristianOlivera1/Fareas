import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { MessageService } from 'primeng/api';

import { ScheduleImportPage } from './schedule-import';

const API = 'http://localhost:8000/api/v1';

describe('ScheduleImportPage', () => {
  let component: ScheduleImportPage;
  let httpMock: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [ScheduleImportPage],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([]),
        MessageService,
      ],
    }).compileComponents();

    component = TestBed.createComponent(ScheduleImportPage).componentInstance;
    httpMock = TestBed.inject(HttpTestingController);

    httpMock.expectOne(`${API}/settings`).flush({
      semester_label: '2026-II',
      attendance_hour_start: '07:00:00',
      attendance_hour_end: '20:00:00',
    });
    httpMock.expectOne(`${API}/teachers?page_size=100`).flush({
      items: [{ id: 3, full_name: 'Docente de Prueba' }],
      total: 1,
      page: 1,
      page_size: 100,
    });
    httpMock.expectOne(`${API}/rooms?page_size=100`).flush({
      items: [{ id: 7, code: 'LAB 305' }],
      total: 1,
      page: 1,
      page_size: 100,
    });
    httpMock.expectOne(`${API}/courses?page_size=100`).flush({
      items: [{ id: 4, code: 'TSTUI901', name: 'ALGEBRA LINEAL', cycle: 9 }],
      total: 1,
      page: 1,
      page_size: 100,
    });
    await Promise.resolve();
    await Promise.resolve();
  });

  afterEach(() => httpMock.verify());

  it('previsualiza y confirma con docente y aula por defecto', async () => {
    component.onFile(new File(['horario'], 'horario.png', { type: 'image/png' }));
    component.semester.set('2026-II');
    component.cycle.set(9);

    const reading = component.readSchedule();
    const preview = httpMock.expectOne(`${API}/courses/import-pdf`);
    expect(preview.request.method).toBe('POST');
    expect(preview.request.body instanceof FormData).toBe(true);
    preview.flush({
      tipo: 'imagen',
      paginas: 1,
      total: 1,
      confiables: 1,
      ambiguousos: 0,
      bloques: [
        {
          course_code: 'TSTUI901',
          course_name: 'ALGEBRA LINEAL',
          group_code: 'A',
          weekday: 1,
          start_time: '07:00',
          end_time: '09:00',
          confiable: true,
          nota: null,
          linea: 'TSTUI901 ALGEBRA LINEAL GRUPO A LUNES 07:00 - 09:00',
          pagina: 1,
          confianza: 0.98,
        },
      ],
    });
    await reading;

    expect(component.step()).toBe(2);
    expect(component.rows().length).toBe(1);
    expect(component.rows()[0].teacher_id).toBeNull();
    expect(component.rows()[0].room_id).toBeNull();
    expect(component.canConfirm()).toBe(true);

    component.onDefaultTeacher(3);
    component.onDefaultRoom(7);
    expect(component.rows()[0].teacher_id).toBe(3);
    expect(component.rows()[0].room_id).toBe(7);
    expect(component.canConfirm()).toBe(true);

    const confirming = component.confirm();
    const confirm = httpMock.expectOne(`${API}/courses/import-pdf/confirm`);
    expect(confirm.request.method).toBe('POST');
    expect(confirm.request.body).toEqual({
      teacher_id: 3,
      room_id: 7,
      cycle: 9,
      semester_label: '2026-II',
      bloques: [
        {
          course_code: 'TSTUI901',
          course_name: 'ALGEBRA LINEAL',
          group_code: 'A',
          weekday: 1,
          start_time: '07:00',
          end_time: '09:00',
          teacher_id: 3,
          room_id: 7,
        },
      ],
    });
    confirm.flush({
      cursos_creados: ['TSTUI901'],
      grupos_creados: ['TSTUI901-A'],
      bloques_creados: 1,
      omitidos: 0,
      total_bloques: 1,
    });
    await confirming;

    expect(component.step()).toBe(3);
    expect(component.result()?.bloques_creados).toBe(1);
  });

  it('el docente y el aula por defecto no pisan los elegidos a mano', async () => {
    component.onFile(new File(['horario'], 'horario.png', { type: 'image/png' }));
    component.semester.set('2026-II');
    component.cycle.set(9);

    const reading = component.readSchedule();
    const block = {
      course_code: 'TSTUI901',
      course_name: 'ALGEBRA LINEAL',
      group_code: 'A',
      start_time: '07:00',
      end_time: '09:00',
      confiable: true,
      nota: null,
      linea: '',
      pagina: 1,
      confianza: 0.98,
    };
    httpMock.expectOne(`${API}/courses/import-pdf`).flush({
      tipo: 'imagen',
      paginas: 1,
      total: 2,
      confiables: 2,
      ambiguousos: 0,
      bloques: [
        { ...block, weekday: 1 },
        { ...block, weekday: 2, room_code: 'LAB 3O5', room_id: null },
      ],
    });
    await reading;

    const [first, second] = component.rows();
    expect(component.hintsFor(second).rooms[0]?.value).toBe(7);
    component.onRowRoom(first.key, 7);
    component.onDefaultRoom(9);

    expect(component.rows().find((row) => row.key === first.key)?.room_id).toBe(7);
    expect(component.rows().find((row) => row.key === second.key)?.room_id).toBe(9);

    component.onRowRoom(first.key, null);
    expect(component.rows().find((row) => row.key === first.key)?.room_id).toBe(9);
  });

  it('resuelve una sugerencia de curso antes de confirmar', async () => {
    component.onFile(new File(['horario'], 'horario.png', { type: 'image/png' }));
    component.semester.set('2026-II');
    component.cycle.set(9);

    const reading = component.readSchedule();
    const preview = httpMock.expectOne(`${API}/courses/import-pdf`);
    preview.flush({
      tipo: 'imagen',
      paginas: 1,
      total: 1,
      confiables: 1,
      ambiguousos: 0,
      bloques: [
        {
          course_code: 'TSTUI9O1',
          course_name: 'ALGEBRA LINEAL',
          group_code: 'A',
          teacher_name: 'Docente de Prueba',
          teacher_id: 3,
          room_code: 'LAB 305',
          room_id: 7,
          weekday: 1,
          start_time: '07:00',
          end_time: '09:00',
          confiable: true,
          nota: null,
          linea: 'TSTUI9O1 ALGEBRA LINEAL GRUPO A LUNES 07:00 - 09:00',
          pagina: 1,
          confianza: 0.98,
          curso_sugerido: {
            id: 4,
            code: 'TSTUI901',
            name: 'ALGEBRA LINEAL',
            cycle: 9,
            score: 0.92,
            motivo: 'código parecido',
          },
        },
      ],
    });
    await reading;

    expect(component.rows()[0].teacher_id).toBe(3);
    expect(component.rows()[0].room_id).toBe(7);
    expect(component.canConfirm()).toBe(false);
    expect(component.pendingSuggestion(component.groups()[0])).toBe(true);

    component.applyCourseSuggestion(component.groups()[0]);

    expect(component.rows()[0].course_code).toBe('TSTUI901');
    expect(component.canConfirm()).toBe(true);
  });
});
