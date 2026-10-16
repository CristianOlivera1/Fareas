import {
  ChangeDetectionStrategy,
  Component,
  CUSTOM_ELEMENTS_SCHEMA,
  effect,
  inject,
  signal,
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import { MessageService } from 'primeng/api';
import { DialogModule } from 'primeng/dialog';
import { InputTextModule } from 'primeng/inputtext';

import { QueryParams } from '../../../shared/utils/query-params';
import { extractDetail } from '../../../shared/utils/api-error';
import { CoursesApi } from '../../../core/services/courses-api';
import { AuthService } from '../../../core/services/auth/auth';
import { PageHeader } from '../../../shared/components/page-header/page-header';
import { UiButton } from '../../../shared/components/ui-button/ui-button';
import { UiInput } from '../../../shared/components/ui-input/ui-input';
import { UiAlert } from '../../../shared/components/ui-alert/ui-alert';
import { DataTable } from '../../../shared/components/data-table/data-table';
import { DataTableCellDirective } from '../../../shared/components/data-table/data-table-cell.directive';
import { TableColumn } from '../../../core/models/table-column';
import { Course } from '../../../core/models/catalog';

interface CourseForm {
  id: number | null;
  code: string;
  name: string;
}

/** F2 · Cursos y grupos: primer nivel de la malla académica (RF-06).
 * El detalle del curso (grupos + horario) vive en `/courses/:courseId`. */
@Component({
  selector: 'app-courses-page',
  imports: [
    FormsModule, PageHeader, UiButton, UiInput, UiAlert, DataTable, DataTableCellDirective,
    DialogModule, InputTextModule,
  ],
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  templateUrl: './courses.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class CoursesPage {
  protected readonly auth = inject(AuthService);
  private readonly api = inject(CoursesApi);
  private readonly qp = inject(QueryParams);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly toast = inject(MessageService);

  readonly columns: TableColumn[] = [
    { id: 'index', header: 'N°', width: '60px', align: 'center' },
    { id: 'code', header: 'Código' },
    { id: 'name', header: 'Curso' },
    { id: 'actions', header: 'Grupos y horario', align: 'right', width: '170px' },
  ];

  readonly q = this.qp.filter('q');
  readonly page = this.qp.number('page', 1);
  readonly pageSize = this.qp.number('page_size', 10);

  readonly courses = signal<Course[]>([]);
  readonly total = signal(0);
  readonly loading = signal(false);
  readonly error = signal<string | null>(null);
  readonly saving = signal(false);

  readonly form = signal<CourseForm>({ id: null, code: '', name: '' });

  dialogVisible = false;

  constructor() {
    effect(() => {
      this.q();
      this.page();
      this.pageSize();
      void this.load();
    });
  }

  patch(p: Partial<CourseForm>): void {
    this.form.update((f) => ({ ...f, ...p }));
  }

  onSearch(value: string): void {
    void this.qp.update({ q: value || null, page: null });
  }

  onPage(p: number): void {
    void this.qp.update({ page: p });
  }

  onPageSize(size: number): void {
    void this.qp.update({ page_size: size, page: null });
  }

  reload(): void {
    void this.load();
  }

  openCreate(): void {
    this.form.set({ id: null, code: '', name: '' });
    this.dialogVisible = true;
  }

  /** Navega al detalle pasando código y nombre (la API de grupos no
   * devuelve el curso cuando todavía no tiene grupos). La ruta es RELATIVA:
   * el panel vive bajo /admin. */
  verGrupos(course: Course): void {
    void this.router.navigate([course.id], {
      relativeTo: this.route,
      queryParams: { code: course.code, name: course.name },
    });
  }

  async save(): Promise<void> {
    const f = this.form();
    if (f.code.trim().length < 3 || f.name.trim().length < 3) {
      this.toast.add({
        severity: 'warn',
        summary: 'Revisa el formulario',
        detail: 'El código y el nombre necesitan al menos 3 caracteres',
        life: 3500,
      });
      return;
    }
    this.saving.set(true);
    try {
      await this.api
        .createCourse({ code: f.code.trim().toUpperCase(), name: f.name.trim() })
        .toPromise();
      this.toast.add({
        severity: 'success',
        summary: 'Curso creado',
        detail: 'Ahora crea sus grupos (A, B, C…) y el horario',
        life: 3500,
      });
      this.dialogVisible = false;
      void this.load();
    } catch (err) {
      this.toast.add({
        severity: 'error',
        summary: 'No se pudo crear el curso',
        detail: extractDetail(err),
        life: 4500,
      });
    } finally {
      this.saving.set(false);
    }
  }

  private async load(): Promise<void> {
    this.loading.set(true);
    this.error.set(null);
    try {
      const res = await this.api
        .courses({ page: this.page(), page_size: this.pageSize(), q: this.q() })
        .toPromise();
      this.courses.set(res?.items ?? []);
      this.total.set(res?.total ?? 0);
    } catch (err) {
      this.error.set(extractDetail(err));
    } finally {
      this.loading.set(false);
    }
  }
}
