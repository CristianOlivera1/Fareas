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
import { Avatar } from '../../../shared/components/avatar/avatar';
import { TableColumn } from '../../../core/models/table-column';
import { EnrolledStudent, Group } from '../../../core/models/catalog';
import { toRoman } from '../../../shared/utils/cycles';

interface Option<T> {
  label: string;
  value: T;
}

@Component({
  selector: 'app-enrollments-page',
  imports: [
    FormsModule, PageHeader, UiButton, UiAlert, ModalDelete, DataTable,
    DataTableCellDirective, DialogModule, SelectModule, Avatar,
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

  readonly roman = toRoman;
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
    { id: 'face', header: 'Rostro', align: 'center', hiddenOnMobile: true },
    { id: 'semester', header: 'Ciclo', align: 'center', hiddenOnMobile: true },
    { id: 'status', header: 'Matrícula', align: 'center' },
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
      label: `Ciclo ${toRoman(g.cycle)} · Grupo ${g.group_code} · ${g.enrolled_count}/${g.capacity}`,
      value: g.id,
    })),
  );

  readonly selectedGroup = computed(
    () => this.groups().find((group) => group.id === this.groupIdNumber()) ?? null,
  );

  readonly activeEnrollmentCount = computed(
    () => this.students().filter((student) => !student.withdrawn_at).length,
  );

  readonly remainingCapacity = computed(() => {
    const group = this.selectedGroup();
    return group ? Math.max(0, group.capacity - this.activeEnrollmentCount()) : 0;
  });

  readonly transferGroupOptions = computed<Option<number>[]>(() => {
    const sourceGroup = this.selectedGroup();
    if (!sourceGroup) return [];
    return this.groups()
      .filter(
        (group) =>
          group.id !== sourceGroup.id &&
          group.is_active &&
          group.enrolled_count < group.capacity,
      )
      .map((group) => ({
        label: `Ciclo ${toRoman(group.cycle)} · Grupo ${group.group_code} · ${group.enrolled_count}/${group.capacity}`,
        value: group.id,
      }));
  });

  constructor() {
    void this.init();
  }

  private async init(): Promise<void> {
    try {
      const [settings, semesterLabels, coursePage] = await Promise.all([
        this.calendar.settings().toPromise(),
        this.calendar.semesters().toPromise(),
        this.api.courses({ page_size: 100 }).toPromise(),
      ]);
      const currentSemester = settings?.semester_label ?? null;
      this.semesters.set(
        [...new Set([currentSemester ?? '', ...(semesterLabels ?? [])])].filter(
          (semester) => semester !== '',
        ),
      );
      this.courseOptions.set(
        (coursePage?.items ?? []).map((course) => ({
          label: `${course.code} · ${course.name}`,
          value: course.id,
        })),
      );
      if (!this.semester() && currentSemester) {
        await this.qp.update({ semester: currentSemester });
      }
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
    const selectedSemester = semesterOverride ?? this.semester();
    this.loadingGroups.set(true);
    this.error.set(null);
    try {
      const courseGroups = await this.api.courseGroups(courseId, selectedSemester).toPromise();
      this.groups.set(courseGroups ?? []);
      if (
        this.groupId() &&
        !(courseGroups ?? []).some((group) => group.id === this.groupIdNumber())
      ) {
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
      const enrolledStudents = await this.api.enrolled(groupId, true).toPromise();
      this.students.set(enrolledStudents ?? []);
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
      const studentPage = await this.catalog
        .students({ q: term || null, page_size: 20, with_face: 'true' })
        .toPromise();
      this.studentOptions.set(
        (studentPage?.items ?? []).map((student) => ({
          label: `${student.code ?? 'sin código'} · ${student.full_name}`,
          value: student.id,
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
      const enrollment = await this.api.enroll(groupId, studentId).toPromise();
      this.toast.add({
        severity: 'success',
        summary: 'Matrícula registrada',
        detail: enrollment?.message ?? 'Alumno matriculado',
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
    const sourceGroupId = this.groupIdNumber();
    const targetGroupId = this.transferTargetId();
    const student = this.transferStudent();
    if (!sourceGroupId || !targetGroupId || !student) {
      this.toast.add({ severity: 'warn', summary: 'Selecciona el grupo destino', life: 3000 });
      return;
    }
    this.saving.set(true);
    try {
      const transfer = await this.api
        .transfer(sourceGroupId, student.id, targetGroupId)
        .toPromise();
      this.toast.add({
        severity: 'success',
        summary: 'Alumno transferido',
        detail: transfer?.message ?? 'Las faltas anteriores se conservan (suman al curso)',
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

  askToWithdraw(student: EnrolledStudent): void {
    this.deleteStudent.set(student);
    this.deleteVisible = true;
  }

  withdrawalLabel(): string | null {
    return this.deleteStudent()?.full_name ?? null;
  }

  cancelWithdrawal(): void {
    this.deleteStudent.set(null);
    this.deleteVisible = false;
  }

  async confirmWithdrawal(): Promise<void> {
    const groupId = this.groupIdNumber();
    const student = this.deleteStudent();
    if (!groupId || !student) return;
    this.deleting.set(true);
    try {
      const enrollment = await this.api.unenroll(groupId, student.id).toPromise();
      this.toast.add({
        severity: 'success',
        summary: 'Matrícula retirada',
        detail: enrollment?.message ?? 'El historial del curso se conserva',
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

  async reactivate(student: EnrolledStudent): Promise<void> {
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

}
