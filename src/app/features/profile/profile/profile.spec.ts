import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';

import { ProfilePage } from './profile';

const API = 'http://localhost:8000/api/v1';

describe('ProfilePage', () => {
  let component: ProfilePage;
  let fixture: ComponentFixture<ProfilePage>;
  let httpMock: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [ProfilePage],
      providers: [provideHttpClient(), provideHttpClientTesting()],
    }).compileComponents();

    fixture = TestBed.createComponent(ProfilePage);
    component = fixture.componentInstance;
    httpMock = TestBed.inject(HttpTestingController);

    fixture.detectChanges();
    httpMock.expectOne(`${API}/auth/me`).flush({
      id: 7,
      role: 'docente',
      full_name: 'Docente de Pruebas',
      email: 'docente@unamba.edu.pe',
      must_change_password: false,
    });
    await fixture.whenStable();
  });

  afterEach(() => httpMock.verify());

  it('should create', () => {
    expect(component).toBeTruthy();
    expect(component.step()).toBe(1);
  });

  it('valida el formato de la contraseña nueva y muestra una indicación clara', () => {
    component.step.set(3);
    const password = component.form.controls.new_password;

    password.setValue('a'.repeat(129));
    password.markAsTouched();

    expect(password.invalid).toBe(true);
    expect(component.fieldError('new_password')).toBe('No puede superar los 128 caracteres.');

    password.setValue('soloLetras');

    expect(password.invalid).toBe(true);
    expect(component.fieldError('new_password')).toBe(
      'Usa entre 8 y 128 caracteres, con al menos una letra y un número.',
    );
  });

  it('valida en tiempo real que ambas contraseñas coincidan', () => {
    component.step.set(3);
    const password = component.form.controls.new_password;
    const confirmation = component.form.controls.confirm_password;

    password.setValue('NuevaClave99');
    confirmation.setValue('NuevaClave98');
    confirmation.markAsTouched();
    fixture.detectChanges();

    expect(confirmation.hasError('mismatch')).toBe(true);
    expect(component.fieldError('confirm_password')).toBe('Las contraseñas no coinciden.');

    password.setValue('NuevaClave98');

    expect(confirmation.valid).toBe(true);
    expect(component.fieldError('confirm_password')).toBe('');
  });

  it('presenta errores de política del servidor junto al campo sin mostrar new_password', () => {
    component.step.set(3);
    component.form.controls.current_password.setValue('ClaveActual1');
    component.form.controls.otp_code.setValue('123456');
    component.form.controls.new_password.setValue('NuevaClave99');
    component.form.controls.confirm_password.setValue('NuevaClave99');

    component.onSubmit();

    const request = httpMock.expectOne(`${API}/auth/change-password`);
    request.flush(
      { detail: 'new_password: Value error, La contraseña debe tener al menos 8 caracteres e incluir letras y números' },
      { status: 422, statusText: 'Unprocessable Entity' },
    );

    expect(component.errorMessage()).not.toContain('new_password');
    expect(component.fieldError('new_password')).toBe(
      'Usa entre 8 y 128 caracteres, con al menos una letra y un número.',
    );
  });

  it('recorre identidad → código → nueva contraseña y actualiza', () => {
    component.form.controls.current_password.setValue('ClaveActual1');

    component.onSubmit();
    const otpRequest = httpMock.expectOne(`${API}/auth/change-password/otp`);
    expect(otpRequest.request.method).toBe('POST');
    expect(otpRequest.request.body).toEqual({ current_password: 'ClaveActual1' });
    otpRequest.flush({
      message: 'Código enviado',
      email: 'do*****e@unamba.edu.pe',
      expires_in: 600,
      resend_in: 60,
    });

    expect(component.step()).toBe(2);
    expect(component.maskedEmail()).toBe('do*****e@unamba.edu.pe');

    component.form.controls.otp_code.setValue('123456');
    component.onSubmit();
    const verifyRequest = httpMock.expectOne(`${API}/auth/change-password/otp/verify`);
    expect(verifyRequest.request.body).toEqual({ code: '123456' });
    verifyRequest.flush({ message: 'Código validado' });

    expect(component.step()).toBe(3);

    component.form.controls.new_password.setValue('NuevaClave99');
    component.form.controls.confirm_password.setValue('NuevaClave99');
    component.onSubmit();

    const changeRequest = httpMock.expectOne(`${API}/auth/change-password`);
    expect(changeRequest.request.body).toEqual({
      current_password: 'ClaveActual1',
      new_password: 'NuevaClave99',
    });
    changeRequest.flush({ message: 'Contraseña actualizada', access_token: 'nuevo-token' });

    expect(component.successMessage()).toContain('Contraseña actualizada');
    expect(component.step()).toBe(1);
  });
});
