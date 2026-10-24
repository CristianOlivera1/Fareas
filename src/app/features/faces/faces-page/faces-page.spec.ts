import { Component } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';
import { MessageService } from 'primeng/api';
import { of } from 'rxjs';

import { Person } from '../../../core/models/catalog';
import { CatalogApi } from '../../../core/services/catalog-api';
import { FacesApi } from '../../../core/services/faces-api';
import { FacesPage } from './faces-page';

@Component({ standalone: true, template: '' })
class RoutePage {}

const student: Person = {
  id: 42,
  role: 'estudiante',
  full_name: 'Ana Torres',
  email: 'ana@unamba.edu.pe',
  dni: '12345678',
  code: '221181',
  whatsapp: null,
  semester: 1,
  is_active: true,
  must_change_password: false,
};

describe('FacesPage query parameters', () => {
  let router: Router;
  let catalog: {
    account: ReturnType<typeof vi.fn>;
    students: ReturnType<typeof vi.fn>;
  };
  let faces: {
    status: ReturnType<typeof vi.fn>;
  };

  beforeEach(async () => {
    catalog = {
      account: vi.fn(() => of(student)),
      students: vi.fn(() => of({ items: [student], total: 1, page: 1, page_size: 8 })),
    };
    faces = {
      status: vi.fn(() =>
        of({
          student_id: student.id,
          enrolled: false,
          photo_url: null,
          source: null,
          created_at: null,
        }),
      ),
    };

    await TestBed.configureTestingModule({
      imports: [FacesPage],
      providers: [
        provideRouter([{ path: 'admin/faces', component: RoutePage }]),
        MessageService,
        { provide: CatalogApi, useValue: catalog },
        { provide: FacesApi, useValue: faces },
      ],
    }).compileComponents();

    router = TestBed.inject(Router);
  });

  it('writes the selected student to the URL without losing the page context', async () => {
    await router.navigateByUrl('/admin/faces?tab=enrollment#student-list');
    const fixture = TestBed.createComponent(FacesPage);
    const page = fixture.componentInstance;

    await page.select(student);

    const url = router.parseUrl(router.url);
    expect(url.queryParamMap.get('student')).toBe(String(student.id));
    expect(url.queryParamMap.get('tab')).toBe('enrollment');
    expect(url.fragment).toBe('student-list');
    expect(page.selected()).toEqual(student);
    expect(page.status()?.student_id).toBe(student.id);
  });

  it('restores a student from a valid URL parameter', async () => {
    await router.navigateByUrl(`/admin/faces?student=${student.id}`);
    const fixture = TestBed.createComponent(FacesPage);
    fixture.detectChanges();
    await fixture.whenStable();
    await new Promise((resolve) => setTimeout(resolve, 0));

    expect(catalog.account).toHaveBeenCalledWith(student.id);
    expect(fixture.componentInstance.selected()).toEqual(student);
    expect(fixture.componentInstance.status()?.student_id).toBe(student.id);
  });

  it('removes invalid student identifiers from the URL', async () => {
    await router.navigateByUrl('/admin/faces?student=12.5');
    const fixture = TestBed.createComponent(FacesPage);
    fixture.detectChanges();
    await fixture.whenStable();
    await new Promise((resolve) => setTimeout(resolve, 0));

    expect(catalog.account).not.toHaveBeenCalled();
    expect(router.parseUrl(router.url).queryParamMap.has('student')).toBe(false);
    expect(fixture.componentInstance.error()).toContain('identificador');
  });
});
