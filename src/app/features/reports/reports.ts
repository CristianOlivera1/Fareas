import {
  ChangeDetectionStrategy,
  Component,
  CUSTOM_ELEMENTS_SCHEMA,
  computed,
  inject,
  signal,
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MessageService } from 'primeng/api';
import { SelectModule } from 'primeng/select';
import { Observable } from 'rxjs';

import { Course, Group } from '../../core/models/catalog';
import { AuthService } from '../../core/services/auth/auth';
import { CoursesApi } from '../../core/services/courses-api';
import { ReportFile, ReportsApi } from '../../core/services/reports-api';
import { extractDetail } from '../../shared/utils/api-error';
import { saveBlob } from '../../shared/utils/download';
import { PageHeader } from '../../shared/components/page-header/page-header';
import { UiButton } from '../../shared/components/ui-button/ui-button';

type BusyKey = 'xlsx' | 'pdf' | 'matrix' | 'dpi';

const RANGE_DAYS = 30;

function isoDay(offsetDays = 0): string {
  const date = new Date();
  date.setDate(date.getDate() + offsetDays);
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${date.getFullYear()}-${month}-${day}`;
}

@Component({
  selector: 'app-reports-page',
  imports: [FormsModule, SelectModule, PageHeader, UiButton],
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  templateUrl: './reports.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { class: 'block' },
})
export class ReportsPage {
  private readonly api = inject(ReportsApi);
  private readonly coursesApi = inject(CoursesApi);
  private readonly auth = inject(AuthService);
  private readonly toast = inject(MessageService);

  readonly from = signal(isoDay(-RANGE_DAYS));
  readonly to = signal(isoDay());
  readonly courseId = signal<number | null>(null);
  readonly dpiCourseId = signal<number | null>(null);
  readonly groupId = signal<number | null>(null);
  readonly busy = signal<BusyKey | null>(null);

  readonly courses = signal<Course[]>([]);
  readonly groups = signal<Group[]>([]);

  readonly courseOptions = computed(() => [
    { label: 'Todos los cursos', value: null },
    ...this.courses().map((course) => ({ label: `${course.code} · ${course.name}`, value: course.id })),
  ]);

  readonly groupOptions = computed(() =>
    this.groups().map((group) => ({
      label: `${group.course_code} · Grupo ${group.group_code} · ${group.semester_label}`,
      value: group.id,
    })),
  );

  readonly rangeError = computed(() => {
    if (!this.from() || !this.to()) return 'Indica las dos fechas del periodo.';
    return this.from() > this.to() ? 'La fecha inicial no puede ser posterior a la final.' : null;
  });

  readonly isTeacher = computed(() => this.auth.currentUser()?.role === 'docente');

  constructor() {
    this.coursesApi.courses({ page_size: 100 }).subscribe({
      next: (page) => this.courses.set(page.items),
      error: (err) => this.fail('No se pudieron cargar los cursos', err),
    });
    this.coursesApi.groups().subscribe({
      next: (groups) => this.groups.set(this.ownGroups(groups)),
      error: (err) => this.fail('No se pudieron cargar los grupos', err),
    });
  }

  downloadAttendance(format: 'xlsx' | 'pdf'): void {
    if (this.rangeError()) return;
    this.run(
      format,
      this.api.attendance(format, {
        desde: this.from(),
        hasta: this.to(),
        course_id: this.courseId(),
      }),
    );
  }

  downloadMatrix(): void {
    const groupId = this.groupId();
    if (groupId === null) return;
    this.run('matrix', this.api.groupMatrix(groupId));
  }

  downloadDpiRisk(): void {
    this.run('dpi', this.api.dpiRisk(this.dpiCourseId()));
  }

  private ownGroups(groups: Group[]): Group[] {
    const userId = this.auth.currentUser()?.id;
    return this.isTeacher() ? groups.filter((group) => group.teacher_id === userId) : groups;
  }

  private run(key: BusyKey, request: Observable<ReportFile>): void {
    this.busy.set(key);
    request.subscribe({
      next: (file) => {
        saveBlob(file.blob, file.filename);
        this.toast.add({ severity: 'success', summary: 'Reporte descargado', detail: file.filename, life: 3000 });
        this.busy.set(null);
      },
      error: async (err) => {
        this.busy.set(null);
        this.fail('No se pudo generar el reporte', await this.readBlobError(err));
      },
    });
  }

  private async readBlobError(err: unknown): Promise<unknown> {
    const body = (err as { error?: unknown }).error;
    if (!(body instanceof Blob)) return err;
    try {
      return { error: JSON.parse(await body.text()) };
    } catch {
      return err;
    }
  }

  private fail(summary: string, err: unknown): void {
    this.toast.add({ severity: 'error', summary, detail: extractDetail(err), life: 4500 });
  }
}
