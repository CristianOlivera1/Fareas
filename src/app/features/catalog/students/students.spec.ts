import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { MessageService } from 'primeng/api';

import { StudentsPage } from './students';

const API = 'http://localhost:8000/api/v1';

describe('StudentsPage', () => {
  let fixture: ComponentFixture<StudentsPage>;
  let component: StudentsPage;
  let httpMock: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [StudentsPage],
      providers: [
        MessageService,
        provideRouter([]),
        provideHttpClient(),
        provideHttpClientTesting(),
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(StudentsPage);
    component = fixture.componentInstance;
    httpMock = TestBed.inject(HttpTestingController);
    fixture.detectChanges();

    httpMock
      .match((request) => request.url === `${API}/settings`)
      .forEach((request) => request.flush({ semester_label: '2026-II' }));
    await Promise.resolve();
    httpMock
      .match((request) => request.url === `${API}/groups`)
      .forEach((request) => request.flush([]));
    httpMock
      .match((request) => request.url === `${API}/students`)
      .forEach((request) =>
        request.flush({ items: [], total: 0, page: 1, page_size: 10 }),
      );
    await Promise.resolve();
  });

  afterEach(() => httpMock.verify());

  function fillValidForm(): void {
    component.studentForm.setValue({
      full_name: 'Ana Torres',
      email: 'ana@unamba.edu.pe',
      dni: '12345678',
      code: '123456',
      semester: 1,
      whatsapp: '+51 983 000 000',
      is_active: true,
    });
  }

  it('validates optional DNI, code, institutional email and Peru WhatsApp', () => {
    component.openCreate();
    component.studentForm.setValue({
      full_name: 'Ana Torres',
      email: 'ana@gmail.com',
      dni: '1234567',
      code: '12345',
      semester: 1,
      whatsapp: '123456789',
      is_active: true,
    });

    expect(component.studentForm.valid).toBe(false);
    expect(component.studentForm.controls.dni.hasError('pattern')).toBe(true);
    expect(component.studentForm.controls.code.hasError('pattern')).toBe(true);
    expect(component.studentForm.controls.email.hasError('institutional')).toBe(true);
    expect(component.studentForm.controls.whatsapp.hasError('whatsapp')).toBe(true);

    fillValidForm();
    expect(component.studentForm.valid).toBe(true);

    component.studentForm.controls.dni.setValue('');
    expect(component.studentForm.valid).toBe(true);
  });

  it('keeps only digits in DNI and code', () => {
    component.openCreate();
    component.studentForm.controls.dni.setValue('12a34-5678');
    component.studentForm.controls.code.setValue('12a34-56');

    expect(component.studentForm.controls.dni.value).toBe('12345678');
    expect(component.studentForm.controls.code.value).toBe('123456');
  });

  it('renders DNI and code as text inputs with numeric keypads', () => {
    component.openCreate();
    fixture.detectChanges();

    const inputs = Array.from(
      (fixture.nativeElement as HTMLElement).querySelectorAll('app-ui-input input'),
    ) as HTMLInputElement[];
    const dni = inputs.find((input) => input.placeholder === '8 dígitos');
    const code = inputs.find((input) => input.placeholder === '221181');

    expect(dni?.type).toBe('text');
    expect(dni?.inputMode).toBe('numeric');
    expect(dni?.maxLength).toBe(8);
    expect(code?.type).toBe('text');
    expect(code?.inputMode).toBe('numeric');
    expect(code?.maxLength).toBe(6);
  });

  it('normalizes the WhatsApp before creating the student', async () => {
    component.openCreate();
    fillValidForm();

    const saving = component.save();
    const request = httpMock.expectOne(`${API}/students`);
    expect(request.request.method).toBe('POST');
    expect(request.request.body.whatsapp).toBe('983000000');
    request.flush({
      id: 1,
      role: 'estudiante',
      full_name: 'Ana Torres',
      email: 'ana@unamba.edu.pe',
      dni: '12345678',
      code: '123456',
      whatsapp: '983000000',
      semester: 1,
      is_active: true,
      must_change_password: true,
    });
    await saving;

    httpMock
      .match((pending) => pending.url === `${API}/students`)
      .forEach((pending) =>
        pending.flush({ items: [], total: 0, page: 1, page_size: 10 }),
      );
  });

  it('disables create-only fields while editing', () => {
    component.openEdit({
      id: 1,
      role: 'estudiante',
      full_name: 'Ana Torres',
      email: 'ana@unamba.edu.pe',
      dni: '12345678',
      code: '123456',
      whatsapp: null,
      semester: 1,
      is_active: true,
      must_change_password: false,
    });

    expect(component.studentForm.controls.email.disabled).toBe(true);
    expect(component.studentForm.controls.dni.disabled).toBe(true);
    expect(component.studentForm.controls.code.disabled).toBe(true);
    expect(component.studentForm.controls.semester.disabled).toBe(true);
    expect(component.studentForm.valid).toBe(true);
  });
});
