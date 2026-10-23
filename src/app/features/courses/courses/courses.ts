import {
  ChangeDetectionStrategy,
  Component,
  CUSTOM_ELEMENTS_SCHEMA,
  computed,
  effect,
  inject,
  signal,
  viewChild,
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import { MessageService } from 'primeng/api';
import { DialogModule } from 'primeng/dialog';
import { InputTextModule } from 'primeng/inputtext';
import { SelectModule } from 'primeng/select';

import { QueryParams } from '../../../shared/utils/query-params';
import { extractDetail } from '../../../shared/utils/api-error';
import { CoursesApi } from '../../../core/services/courses-api';
import { AuthService } from '../../../core/services/auth/auth';
import { PageHeader } from '../../../shared/components/page-header/page-header';
import { UiButton } from '../../../shared/components/ui-button/ui-button';
import { UiInput } from '../../../shared/components/ui-input/ui-input';
import { UiAlert } from '../../../shared/components/ui-alert/ui-alert';
import { ModalDelete } from '../../../shared/components/modal-delete/modal-delete';
import { DataTable } from '../../../shared/components/data-table/data-table';
import { DataTableCellDirective } from '../../../shared/components/data-table/data-table-cell.directive';
import { TableColumn } from '../../../core/models/table-column';
import { Course } from '../../../core/models/catalog';
import { CYCLES, toRoman } from '../../../shared/utils/cycles';

interface CourseForm {
  id: number | null;
  code: string;
  name: string;
  cycle: number | null;
}

@Component({
  selector: 'app-courses-page',
  imports: [
    FormsModule, PageHeader, UiButton, UiInput, UiAlert, ModalDelete, DataTable,
    DataTableCellDirective, DialogModule, InputTextModule, SelectModule,
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
  private readonly deleteModal = viewChild(ModalDelete);

  readonly columns: TableColumn[] = [
    { id: 'index', header: 'N°', width: '60px', align: 'center' },
    { id: 'code', header: 'Código' },
    { id: 'name', header: 'Curso' },
    { id: 'cycle', header: 'Ciclo', align: 'center', width: '90px' },
    { id: 'actions', header: 'Acciones', align: 'right', width: '240px' },
  ];

  readonly cycles = CYCLES;
  readonly cycleOptions = CYCLES.map((cycle) => ({ label: `Ciclo ${toRoman(cycle)}`, value: cycle }));
  readonly roman = toRoman;

  readonly q = this.qp.filter('q');
  readonly cycle = this.qp.filter('cycle');
  readonly cycleNumber = computed(() => {
    const raw = this.cycle();
    const value = raw ? Number(raw) : 0;
    return value >= 1 && value <= 10 ? value : 0;
  });
  readonly page = this.qp.number('page', 1);
  readonly pageSize = this.qp.number('page_size', 10);

  readonly courses = signal<Course[]>([]);
  readonly total = signal(0);
  readonly loading = signal(false);
  readonly error = signal<string | null>(null);
  readonly saving = signal(false);

  readonly form = signal<CourseForm>({ id: null, code: '', name: '', cycle: null });
  readonly dialogTitle = computed(() => (this.form().id ? 'Editar curso' : 'Nuevo curso'));
  readonly deleteTarget = signal<Course | null>(null);
  readonly deleting = signal(false);

  dialogVisible = false;
  deleteVisible = false;

  constructor() {
    effect(() => {
      this.q();
      this.cycle();
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

  onCycle(value: number | null): void {
    void this.qp.update({ cycle: value, page: null });
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
    this.form.set({ id: null, code: '', name: '', cycle: this.cycleNumber() || null });
    this.dialogVisible = true;
  }

  openEdit(course: Course): void {
    this.form.set({
      id: course.id,
      code: course.code,
      name: course.name,
      cycle: course.cycle,
    });
    this.dialogVisible = true;
  }

  viewGroups(course: Course): void {
    void this.router.navigate([course.id], {
      relativeTo: this.route,
      queryParams: { code: course.code, name: course.name, cycle: course.cycle },
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
    const cycle = f.cycle;
    if (!cycle) {
      this.toast.add({
        severity: 'warn',
        summary: 'Indica el ciclo del curso',
        detail: 'El ciclo de la malla va del I al X',
        life: 3500,
      });
      return;
    }

    const id = f.id;
    const body = { code: f.code.trim().toUpperCase(), name: f.name.trim(), cycle };
    this.saving.set(true);
    try {
      if (id !== null) {
        await this.api.updateCourse(id, body).toPromise();
      } else {
        await this.api.createCourse(body).toPromise();
      }
      this.toast.add({
        severity: 'success',
        summary: id !== null ? 'Curso actualizado' : 'Curso creado',
        detail:
          id !== null
            ? 'Los cambios se guardaron correctamente'
            : 'Ahora crea sus grupos (A, B, C…) y el horario',
        life: 3500,
      });
      this.dialogVisible = false;
      void this.load();
    } catch (err) {
      this.toast.add({
        severity: 'error',
        summary: id !== null ? 'No se pudo actualizar el curso' : 'No se pudo crear el curso',
        detail: extractDetail(err),
        life: 4500,
      });
    } finally {
      this.saving.set(false);
    }
  }

  askDelete(course: Course): void {
    this.deleteTarget.set(course);
    this.deleteVisible = true;
  }

  deleteLabel(): string | null {
    const course = this.deleteTarget();
    return course ? `${course.code} · ${course.name}` : null;
  }

  deleteWarning(): string | null {
    return (
      'Solo se eliminan cursos sin grupos. Si el curso ya tiene grupos, ' +
      'conserva el historial académico y desactívalos en lugar de borrarlo.'
    );
  }

  cancelDelete(): void {
    this.deleteTarget.set(null);
    this.deleteVisible = false;
  }

  async confirmDelete(): Promise<void> {
    const course = this.deleteTarget();
    if (!course) return;
    this.deleting.set(true);
    try {
      const res = await this.api.deleteCourse(course.id).toPromise();
      this.toast.add({
        severity: 'success',
        summary: 'Curso eliminado',
        detail: res?.message ?? `El curso ${course.code} se eliminó correctamente`,
        life: 3500,
      });
      void this.load();
    } catch (err) {
      this.toast.add({
        severity: 'error',
        summary: 'No se pudo eliminar el curso',
        detail: extractDetail(err),
        life: 5500,
      });
    } finally {
      this.deleteVisible = false;
      this.deleteTarget.set(null);
      this.deleteModal()?.done();
      this.deleting.set(false);
    }
  }

  private async load(): Promise<void> {
    this.loading.set(true);
    this.error.set(null);
    try {
      const res = await this.api
        .courses({
          page: this.page(),
          page_size: this.pageSize(),
          q: this.q(),
          cycle: this.cycleNumber() || undefined,
        })
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
