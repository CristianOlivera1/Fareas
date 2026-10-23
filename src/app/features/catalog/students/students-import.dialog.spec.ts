import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { MessageService } from 'primeng/api';

import { StudentsImportDialog } from './students-import.dialog';

const API = 'http://localhost:8000/api/v1';

describe('StudentsImportDialog', () => {
  let component: StudentsImportDialog;
  let httpMock: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [StudentsImportDialog],
      providers: [provideHttpClient(), provideHttpClientTesting(), MessageService],
    }).compileComponents();

    component = TestBed.createComponent(StudentsImportDialog).componentInstance;
    httpMock = TestBed.inject(HttpTestingController);

    httpMock.expectOne(`${API}/settings`).flush({ semester_label: '2026-II' });
    await Promise.resolve();
    httpMock
      .expectOne(`${API}/groups?semester=2026-II&include_inactive=false`)
      .flush([]);
    await Promise.resolve();
  });

  afterEach(() => httpMock.verify());

  it('previsualiza la nómina y confirma las filas corregidas', async () => {
    component.onFile(new File(['nomina'], 'nomina.png', { type: 'image/png' }));
    component.defaultSemester.set(9);

    const reading = component.readRoster();
    const preview = httpMock.expectOne(`${API}/students/import-preview`);
    expect(preview.request.method).toBe('POST');
    expect(preview.request.body instanceof FormData).toBe(true);
    preview.flush({
      tipo: 'imagen',
      paginas: 1,
      total: 1,
      listos: 1,
      con_error: 0,
      alumnos: [
        {
          fila: 1,
          code: '999901',
          dni: '70000001',
          full_name: 'PRUEBA UNO',
          email: '999901@unamba.edu.pe',
          email_generado: true,
          semester: 9,
          whatsapp: null,
          confiable: true,
          duplicado: false,
          errores: [],
          nota: null,
          linea: '999901 70000001 PRUEBA UNO',
          pagina: 1,
        },
      ],
    });
    await reading;

    expect(component.step()).toBe(2);
    expect(component.canConfirm()).toBe(true);
    expect(component.rows()[0].email_generado).toBe(true);

    const confirming = component.confirm();
    const confirm = httpMock.expectOne(`${API}/students/import-confirm`);
    expect(confirm.request.method).toBe('POST');
    expect(confirm.request.body).toEqual({
      group_id: null,
      alumnos: [
        {
          fila: 1,
          code: '999901',
          dni: '70000001',
          full_name: 'PRUEBA UNO',
          email: '999901@unamba.edu.pe',
          semester: 9,
          whatsapp: null,
        },
      ],
    });
    confirm.flush({
      creados: 1,
      omitidos: 0,
      matriculados: 0,
      total: 1,
      errores: [],
    });
    await confirming;

    expect(component.step()).toBe(3);
    expect(component.result()?.creados).toBe(1);
  });
});
