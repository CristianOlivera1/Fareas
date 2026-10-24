import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';

import { ProfilePage } from './profile';

const API = 'http://localhost:8000/api/v1';

function status(open: boolean, cycle = 2) {
  return {
    period: '2026-II',
    student_cycle: cycle,
    enrolled_groups: 0,
    window: { open, start: null, end: null, message: open ? 'Matrícula abierta.' : 'La matrícula no está habilitada.' },
  };
}

describe('ProfilePage student cycle', () => {
  let component: ProfilePage;
  let fixture: ComponentFixture<ProfilePage>;
  let httpMock: HttpTestingController;

  async function setup(windowOpen: boolean): Promise<void> {
    await TestBed.configureTestingModule({
      imports: [ProfilePage],
      providers: [provideHttpClient(), provideHttpClientTesting()],
    }).compileComponents();
    fixture = TestBed.createComponent(ProfilePage);
    component = fixture.componentInstance;
    httpMock = TestBed.inject(HttpTestingController);
    fixture.detectChanges();
    httpMock.expectOne(`${API}/auth/me`).flush({
      id: 9,
      role: 'estudiante',
      full_name: 'Alumno de Pruebas',
      email: 'alumno@unamba.edu.pe',
      must_change_password: false,
    });
    await fixture.whenStable();
    fixture.detectChanges();
    httpMock.expectOne(`${API}/me/enrollment`).flush(status(windowOpen));
    await fixture.whenStable();
  }

  afterEach(() => httpMock.verify());

  it('locks the cycle while the enrollment window is closed', async () => {
    await setup(false);

    component.selectCycle(5);

    expect(component.cycleEditable()).toBe(false);
    expect(component.cycleChanged()).toBe(false);
  });

  it('saves the new cycle while the window is open', async () => {
    await setup(true);

    component.selectCycle(3);
    expect(component.cycleChanged()).toBe(true);
    component.saveCycle();

    const request = httpMock.expectOne(`${API}/me/enrollment/cycle`);
    expect(request.request.method).toBe('PATCH');
    expect(request.request.body).toEqual({ cycle: 3 });
    request.flush({ student_cycle: 3 });

    expect(component.enrollmentStatus()?.student_cycle).toBe(3);
    expect(component.cycleSaved()).toBe(true);
    expect(component.cycleChanged()).toBe(false);
  });
});
