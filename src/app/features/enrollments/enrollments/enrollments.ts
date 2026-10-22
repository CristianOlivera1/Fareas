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

import { QueryParams } from '../../../shared/utils/query-params';
import { extractDetail } from '../../../shared/utils/api-error';
import { CoursesApi } from '../../../core/services/courses-api';
import { CatalogApi } from '../../../core/services/catalog-api';
import { CalendarApi } from '../../../core/services/calendar-api';
import { AuthService } from '../../../core/services/auth/auth';
import { PageHeader } from '../../../shared/components/page-header/page-header';
import { UiButton } from '../../../shared/components/ui-button/ui-button';
import { UiAlert } from '../../../shared/components/ui-alert/ui-alert';
import { ModalDelete } from '../../../shared/components/modal-delete/modal-delete';
import { DataTable } from '../../../shared/components/data-table/data-table';
import { DataTableCellDirective } from '../../../shared/components/data-table/data-table-cell.directive';
import { TableColumn } from '../../../core/models/table-column';
import { EnrolledStudent, Group } from '../../../core/models/catalog';

interface Option<T> {
  label: string;
  value: T;
}

@Component({
  selector: 'app-enrollments-page',
  imports: [
    FormsModule, PageHeader, UiButton, UiAlert, ModalDelete, DataTable,
    DataTableCellDirective, DialogModule, SelectModule,
  ],
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  templateUrl: './enrollments.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class EnrollmentsPage {
  protected readonly auth = inject(AuthService);
  private readonly api = inject(CoursesApi);
  private readonly catalog = inject(CatalogApi);
  private readonly calendar = inject(CalendarApi);
  private readonly qp = inject(QueryParams);
  private readonly toast = inject(MessageService);
  private readonly deleteModal = viewChild(ModalDelete);

  readonly semester = this.qp.filter('semester');
  readonly courseId = this.qp.filter('course');
  readonly groupId = this.qp.filter('group');

  readonly courseIdNumber = computed(() => {
    const raw = this.courseId();
    return raw ? Number(raw) : null;
  });
  readonly groupIdNumber = computed(() => {
    const raw = this.groupId();
    return raw ? Number(raw) : null;
  });

  readonly columns: TableColumn[] = [
    { id: 'index', header: 'N°', width: '60px', align: 'center' },
    { id: 'student', header: 'Estudiante' },
    { id: 'rostro', header: 'Rostro', align: 'center', hiddenOnMobile: true },
    { id: 'semester', header: 'Ciclo', align: 'center', hiddenOnMobile: true },
    { id: 'estado', header: 'Matrícula', align: 'center' },
    { id: 'actions', header: 'Acciones', align: 'center', width: '150px' },
  ];

  readonly semesters = signal<string[]>([]);
  readonly courseOptions = signal<Option<number>[]>([]);
  readonly groups = signal<Group[]>([]);
  readonly students = signal<EnrolledStudent[]>([]);

  readonly loadingGroups = signal(false);
  readonly loadingStudents = signal(false);
  readonly error = signal<string | null>(null);
  readonly saving = signal(false);
  readonly deleting = signal(false);

  readonly studentOptions = signal<Option<number>[]>([]);
  readonly selectedStudentId = signal<number | null>(null);
  readonly searchingStudents = signal(false);
  enrollDialogVisible = false;

  readonly transferStudent = signal<EnrolledStudent | null>(null);
  readonly transferTargetId = signal<number | null>(null);
  transferDialogVisible = false;

  readonly deleteStudent = signal<EnrolledStudent | null>(null);
  deleteVisible = false;

  private searchTimer: ReturnType<typeof setTimeout> | null = null;

  readonly groupOptions = computed<Option<number>[]>(() =>
    this.groups().map((g) => ({
      label: `Grupo ${g.group_code} · ${g.enrolled_count}/${g.capacity}`,
      value: g.id,
    })),
  );

  readonly group = computed(() => this.groups().find((g) => g.id === this.groupIdNumber()) ?? null);

  readonly activos = computed(() => this.students().filter((s) => !s.withdrawn_at).length);

  readonly cupoLibre = computed(() => {
    const g = this.group();
    return g ? Math.max(0, g.capacity - this.activos()) : 0;
  });

  readonly transferOptions = computed<Option<number>[]>(() => {
    const origen = this.group();
    if (!origen) return [];
    return this.groups()
      .filter((g) => g.id !== origen.id && g.is_active && g.enrolled_count < g.capacity)
      .map((g) => ({
        label: `Grupo ${g.group_code} · ${g.enrolled_count}/${g.capacity}`,
        value: g.id,
      }));
  });

  constructor() {
    void this.init();
  }

  private async init(): Promise<void> {
    try {
      const [cfg, labels, courses] = await Promise.all([
        this.calendar.settings().toPromise(),
        this.calendar.semesters().toPromise(),
        this.api.courses({ page_size: 100 }).toPromise(),
      ]);
      const vigente = cfg?.semester_label ?? null;
      this.semesters.set([...new Set([vigente ?? '', ...(labels ?? [])])].filter((s) => s !== ''));
      this.courseOptions.set(
        (courses?.items ?? []).map((c) => ({ label: `${c.code} · ${c.name}`, value: c.id })),
      );
      if (!this.semester() && vigente) await this.qp.update({ semester: vigente });
    } catch (err) {
      this.error.set(extractDetail(err));
      return;
    }
    if (this.courseId()) await this.loadGroups();
    if (this.groupId()) await this.loadStudents();
  }

  private async loadGroups(
    semesterOverride?: string | null,
    courseOverride?: number | null,
  ): Promise<void> {
    const courseId = courseOverride ?? this.courseIdNumber();
    if (!courseId) {
      this.groups.set([]);
      return;
    }
    const sem = semesterOverride ?? this.semester();
    this.loadingGroups.set(true);
    this.error.set(null);
    try {
      const list = await this.api.courseGroups(courseId, sem).toPromise();
      this.groups.set(list ?? []);
      if (this.groupId() && !(list ?? []).some((g) => g.id === this.groupIdNumber())) {
        this.students.set([]);
      }
    } catch (err) {
      this.error.set(extractDetail(err));
    } finally {
      this.loadingGroups.set(false);
    }
  }

  private async loadStudents(groupOverride?: number | null): Promise<void> {
    const groupId = groupOverride ?? this.groupIdNumber();
    if (!groupId) {
      this.students.set([]);
      return;
    }
    this.loadingStudents.set(true);
    this.error.set(null);
    try {
      const list = await this.api.enrolled(groupId, true).toPromise();
      this.students.set(list ?? []);
    } catch (err) {
      this.error.set(extractDetail(err));
    } finally {
      this.loadingStudents.set(false);
    }
  }

  onSemester(value: string | null): void {
    this.students.set([]);
    void this.qp.update({ semester: value, group: null });
    if (this.courseId()) void this.loadGroups(value);
    else this.groups.set([]);
  }

  onCourse(value: number | null): void {
    this.students.set([]);
    void this.qp.update({ course: value, group: null });
    if (value) void this.loadGroups(undefined, value);
    else this.groups.set([]);
  }

  onGroup(value: number | null): void {
    void this.qp.update({ group: value });
    if (value) void this.loadStudents(value);
    else this.students.set([]);
  }

  reloadStudents(): void {
    void this.loadStudents();
  }

  openEnroll(): void {
    this.selectedStudentId.set(null);
    this.enrollDialogVisible = true;
    void this.searchStudents('');
  }

  onStudentFilter(event: { filter: string }): void {
    const term = event.filter ?? '';
    if (this.searchTimer) clearTimeout(this.searchTimer);
    this.searchTimer = setTimeout(() => void this.searchStudents(term), 250);
  }

  private async searchStudents(term: string): Promise<void> {
    this.searchingStudents.set(true);
    try {
      const res = await this.catalog
        .students({ q: term || null, page_size: 20, with_face: 'true' })
        .toPromise();
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

  async confirmEnroll(): Promise<void> {
    const groupId = this.groupIdNumber();
    const studentId = this.selectedStudentId();
    if (!groupId || !studentId) {
      this.toast.add({ severity: 'warn', summary: 'Selecciona un estudiante', life: 3000 });
      return;
    }
    this.saving.set(true);
    try {
      const res = await this.api.enroll(groupId, studentId).toPromise();
      this.toast.add({
        severity: 'success',
        summary: 'Matrícula registrada',
        detail: res?.message ?? 'Alumno matriculado',
        life: 3500,
      });
      this.enrollDialogVisible = false;
      await Promise.all([this.loadStudents(), this.loadGroups()]);
    } catch (err) {
      this.toast.add({
        severity: 'error',
        summary: 'No se pudo matricular',
        detail: extractDetail(err),
        life: 6000,
      });
    } finally {
      this.saving.set(false);
    }
  }

  askTransfer(student: EnrolledStudent): void {
    this.transferStudent.set(student);
    this.transferTargetId.set(null);
    this.transferDialogVisible = true;
  }

  async confirmTransfer(): Promise<void> {
    const origen = this.groupIdNumber();
    const destino = this.transferTargetId();
    const student = this.transferStudent();
    if (!origen || !destino || !student) {
      this.toast.add({ severity: 'warn', summary: 'Selecciona el grupo destino', life: 3000 });
      return;
    }
    this.saving.set(true);
    try {
      const res = await this.api.transfer(origen, student.id, destino).toPromise();
      this.toast.add({
        severity: 'success',
        summary: 'Alumno transferido',
        detail: res?.message ?? 'Las faltas anteriores se conservan (suman al curso)',
        life: 4000,
      });
      this.transferDialogVisible = false;
      await Promise.all([this.loadStudents(), this.loadGroups()]);
    } catch (err) {
      this.toast.add({
        severity: 'error',
        summary: 'No se pudo transferir',
        detail: extractDetail(err),
        life: 6000,
      });
    } finally {
      this.saving.set(false);
    }
  }

  askRetirar(student: EnrolledStudent): void {
    this.deleteStudent.set(student);
    this.deleteVisible = true;
  }

  retirarLabel(): string | null {
    return this.deleteStudent()?.full_name ?? null;
  }

  cancelRetirar(): void {
    this.deleteStudent.set(null);
    this.deleteVisible = false;
  }

  async confirmRetirar(): Promise<void> {
    const groupId = this.groupIdNumber();
    const student = this.deleteStudent();
    if (!groupId || !student) return;
    this.deleting.set(true);
    try {
      const res = await this.api.unenroll(groupId, student.id).toPromise();
      this.toast.add({
        severity: 'success',
        summary: 'Matrícula retirada',
        detail: res?.message ?? 'El historial del curso se conserva',
        life: 3500,
      });
      await Promise.all([this.loadStudents(), this.loadGroups()]);
    } catch (err) {
      this.toast.add({
        severity: 'error',
        summary: 'No se pudo retirar',
        detail: extractDetail(err),
        life: 4500,
      });
    } finally {
      this.deleteModal()?.done();
      this.deleting.set(false);
      this.deleteStudent.set(null);
      this.deleteVisible = false;
    }
  }

  async reactivar(student: EnrolledStudent): Promise<void> {
    const groupId = this.groupIdNumber();
    if (!groupId) return;
    try {
      await this.api.enroll(groupId, student.id).toPromise();
      this.toast.add({ severity: 'success', summary: 'Matrícula reactivada', life: 3000 });
      await Promise.all([this.loadStudents(), this.loadGroups()]);
    } catch (err) {
      this.toast.add({
        severity: 'error',
        summary: 'No se pudo reactivar',
        detail: extractDetail(err),
        life: 4500,
      });
    }
  }

  initials(name: string): string {
    const parts = name.trim().split(/\s+/);
    return parts.length >= 2
      ? `${parts[0][0]}${parts[1][0]}`.toUpperCase()
      : name.slice(0, 2).toUpperCase();
  }
}
