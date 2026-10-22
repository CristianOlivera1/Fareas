import {
  ChangeDetectionStrategy,
  Component,
  CUSTOM_ELEMENTS_SCHEMA,
  computed,
  inject,
  signal,
  viewChild,
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MessageService } from 'primeng/api';
import { DialogModule } from 'primeng/dialog';
import { SelectModule } from 'primeng/select';

import { extractDetail } from '../../../shared/utils/api-error';
import { CalendarApi } from '../../../core/services/calendar-api';
import { CatalogApi } from '../../../core/services/catalog-api';
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
import { Justification } from '../../../core/models/catalog';

interface Option<T> {
  label: string;
  value: T;
}

interface JustificationForm {
  student_id: number | null;
  course_id: number | null;
  start_date: string;
  end_date: string;
  reason: string;
  document_url: string;
}

@Component({
  selector: 'app-justifications',
  imports: [
    FormsModule, PageHeader, UiButton, UiInput, UiAlert, ModalDelete, DataTable,
    DataTableCellDirective, DialogModule, SelectModule,
  ],
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  templateUrl: './justifications.page.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class JustificationsPage {
  protected readonly auth = inject(AuthService);
  private readonly api = inject(CalendarApi);
  private readonly catalog = inject(CatalogApi);
  private readonly courses = inject(CoursesApi);
  private readonly toast = inject(MessageService);
  private readonly deleteModal = viewChild(ModalDelete);

  readonly columns: TableColumn[] = [
    { id: 'index', header: 'N°', width: '60px', align: 'center' },
    { id: 'student', header: 'Estudiante' },
    { id: 'curso', header: 'Curso', hiddenOnMobile: true },
    { id: 'rango', header: 'Rango' },
    { id: 'reason', header: 'Motivo', hiddenOnMobile: true },
    { id: 'document', header: 'Documento', align: 'center', hiddenOnMobile: true },
    { id: 'created_by_name', header: 'Registró', hiddenOnMobile: true },
    { id: 'actions', header: 'Acciones', align: 'right', width: '90px' },
  ];

  readonly justifications = signal<Justification[]>([]);
  readonly loading = signal(false);
  readonly error = signal<string | null>(null);
  readonly saving = signal(false);
  readonly deleting = signal(false);

  readonly filterStudentId = signal<number | null>(null);
  readonly filterCourseId = signal<number | null>(null);
  readonly studentOptions = signal<Option<number>[]>([]);
  readonly courseOptions = signal<Option<number>[]>([]);
  readonly searchingStudents = signal(false);
  private searchTimer: ReturnType<typeof setTimeout> | null = null;

  readonly form = signal<JustificationForm>({
    student_id: null,
    course_id: null,
    start_date: '',
    end_date: '',
    reason: '',
    document_url: '',
  });
  createVisible = false;

  readonly deleteTarget = signal<Justification | null>(null);
  deleteVisible = false;

  readonly canSubmit = computed(() => {
    const f = this.form();
    return (
      f.student_id !== null &&
      f.start_date !== '' &&
      f.end_date !== '' &&
      f.end_date >= f.start_date &&
      f.reason.trim().length >= 5 &&
      (this.auth.isAdmin() || f.course_id !== null)
    );
  });

  constructor() {
    void this.init();
  }

  private async init(): Promise<void> {
    try {
      const page = await this.courses.courses({ page_size: 100 }).toPromise();
      this.courseOptions.set(
        (page?.items ?? []).map((c) => ({ label: `${c.code} · ${c.name}`, value: c.id })),
      );
    } catch (err) {
      this.error.set(extractDetail(err));
    }
    await Promise.all([this.searchStudents(''), this.load()]);
  }

  patch(p: Partial<JustificationForm>): void {
    this.form.update((f) => ({ ...f, ...p }));
  }

  onStudentFilter(event: { filter: string }): void {
    const term = event.filter ?? '';
    if (this.searchTimer) clearTimeout(this.searchTimer);
    this.searchTimer = setTimeout(() => void this.searchStudents(term), 250);
  }

  private async searchStudents(term: string): Promise<void> {
    this.searchingStudents.set(true);
    try {
      const res = await this.catalog.students({ q: term || null, page_size: 20 }).toPromise();
      this.studentOptions.set(
        (res?.items ?? []).map((s) => ({
          label: `${s.code ?? 'sin código'} · ${s.full_name}`,
          value: s.id,
        })),
      );
    } catch (err) {
      this.toast.add({
        severity: 'error',
        summary: 'No se pudo buscar estudiantes',
        detail: extractDetail(err),
        life: 4000,
      });
    } finally {
      this.searchingStudents.set(false);
    }
  }

  onFilterStudent(value: number | null): void {
    this.filterStudentId.set(value);
    void this.load();
  }

  onFilterCourse(value: number | null): void {
    this.filterCourseId.set(value);
    void this.load();
  }

  reload(): void {
    void this.load();
  }

  openCreate(): void {
    this.form.set({
      student_id: null,
      course_id: null,
      start_date: '',
      end_date: '',
      reason: '',
      document_url: '',
    });
    this.createVisible = true;
    if (this.studentOptions().length === 0) void this.searchStudents('');
  }

  async save(): Promise<void> {
    const f = this.form();
    if (!this.canSubmit() || f.student_id === null) {
      this.toast.add({
        severity: 'warn',
        summary: 'Revisa el formulario',
        detail: this.auth.isAdmin()
          ? 'Faltan datos: alumno, fechas y motivo (5 caracteres como mínimo)'
          : 'Como docente debes elegir el curso, además del alumno, las fechas y el motivo',
        life: 4500,
      });
      return;
    }
    this.saving.set(true);
    try {
      const res = await this.api
        .createJustification({
          student_id: f.student_id,
          course_id: f.course_id,
          start_date: f.start_date,
          end_date: f.end_date,
          reason: f.reason.trim(),
          document_url: f.document_url.trim() || null,
        })
        .toPromise();
      this.toast.add({
        severity: 'success',
        summary: 'Justificación registrada',
        detail: res?.message ?? `${res?.faltas_afectadas ?? 0} falta(s) justificada(s)`,
        life: 5000,
      });
      this.createVisible = false;
      void this.load();
    } catch (err) {
      this.toast.add({
        severity: 'error',
        summary: 'No se pudo registrar la justificación',
        detail: extractDetail(err),
        life: 5500,
      });
    } finally {
      this.saving.set(false);
    }
  }

  askDelete(j: Justification): void {
    this.deleteTarget.set(j);
    this.deleteVisible = true;
  }

  deleteLabel(): string | null {
    const j = this.deleteTarget();
    return j ? `${j.student_name} · ${this.rangeLabel(j)}` : null;
  }

  cancelDelete(): void {
    this.deleteTarget.set(null);
    this.deleteVisible = false;
  }

  async confirmDelete(): Promise<void> {
    const target = this.deleteTarget();
    if (!target) return;
    this.deleting.set(true);
    try {
      const res = await this.api.deleteJustification(target.id).toPromise();
      this.toast.add({
        severity: 'success',
        summary: 'Justificación eliminada',
        detail: res?.message ?? 'Las faltas volvieron a su estado original',
        life: 5000,
      });
      void this.load();
    } catch (err) {
      this.toast.add({
        severity: 'error',
        summary: 'No se pudo eliminar',
        detail: extractDetail(err),
        life: 4500,
      });
    } finally {
      this.deleteModal()?.done();
      this.deleting.set(false);
      this.deleteTarget.set(null);
      this.deleteVisible = false;
    }
  }

  rangeLabel(j: Pick<Justification, 'start_date' | 'end_date'>): string {
    return j.start_date === j.end_date ? j.start_date : `${j.start_date} → ${j.end_date}`;
  }

  days(j: Pick<Justification, 'start_date' | 'end_date'>): number {
    const start = new Date(`${j.start_date}T12:00:00`).getTime();
    const end = new Date(`${j.end_date}T12:00:00`).getTime();
    return Math.round((end - start) / 86_400_000) + 1;
  }

  private async load(): Promise<void> {
    this.loading.set(true);
    this.error.set(null);
    try {
      const list = await this.api
        .justifications({
          student_id: this.filterStudentId() ?? undefined,
          course_id: this.filterCourseId() ?? undefined,
        })
        .toPromise();
      this.justifications.set(list ?? []);
    } catch (err) {
      this.error.set(extractDetail(err));
    } finally {
      this.loading.set(false);
    }
  }
}
