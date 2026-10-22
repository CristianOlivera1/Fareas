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

  it('recorre identidad → código → nueva contraseña y actualiza', () => {
    component.form.controls.current_password.setValue('ClaveActual1');

    // Enter en el paso 1 también debe enviar el código (onSubmit enruta).
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
    // Enter en el paso 2 verifica el código.
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
