import {
  ChangeDetectionStrategy,
  Component,
  CUSTOM_ELEMENTS_SCHEMA,
  computed,
  inject,
  signal,
} from '@angular/core';

import { AuthService } from '../../core/services/auth/auth';
import { CoursesApi } from '../../core/services/courses-api';
import { StudentPortalApi } from '../../core/services/student-portal-api';
import { ScheduleRow } from '../../core/models/catalog';
import { extractDetail } from '../../shared/utils/api-error';
import { PageHeader } from '../../shared/components/page-header/page-header';
import { UiAlert } from '../../shared/components/ui-alert/ui-alert';
import { UiButton } from '../../shared/components/ui-button/ui-button';
import { ScheduleTable } from '../../shared/components/schedule-table/schedule-table';

@Component({
  selector: 'app-my-schedule-page',
  imports: [PageHeader, UiAlert, UiButton, ScheduleTable],
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  templateUrl: './my-schedule.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { class: 'block' },
})
export class MySchedulePage {
  private readonly auth = inject(AuthService);
  private readonly courses = inject(CoursesApi);
  private readonly portal = inject(StudentPortalApi);

  readonly rows = signal<ScheduleRow[]>([]);
  readonly semester = signal<string | null>(null);
  readonly loading = signal(true);
  readonly error = signal<string | null>(null);

  readonly isTeacher = computed(() => this.auth.currentUser()?.role === 'docente');
  readonly subtitle = computed(() =>
    this.isTeacher()
      ? 'Tus clases de la semana en el periodo vigente.'
      : 'Las clases de los cursos en los que estás matriculado.',
  );
  readonly classCount = computed(() => this.rows().length);

  constructor() {
    this.load();
  }

  load(): void {
    this.loading.set(true);
    this.error.set(null);
    const request = this.isTeacher() ? this.teacherSchedule() : this.portal.schedule();
    request.subscribe({
      next: (rows) => {
        this.rows.set(rows);
        this.semester.set(rows[0]?.semester_label ?? null);
        this.loading.set(false);
      },
      error: (err) => {
        this.error.set(extractDetail(err));
        this.loading.set(false);
      },
    });
  }

  private teacherSchedule() {
    const teacherId = this.auth.currentUser()?.id;
    return this.courses.schedule({ teacher_id: teacherId });
  }
}
