import {
  ChangeDetectionStrategy,
  Component,
  CUSTOM_ELEMENTS_SCHEMA,
  computed,
  inject,
  signal,
} from '@angular/core';
import { DialogModule } from 'primeng/dialog';
import { MessageService } from 'primeng/api';
import { forkJoin } from 'rxjs';

import { EnrolledStudent, Group, ScheduleRow } from '../../core/models/catalog';
import { AuthService } from '../../core/services/auth/auth';
import { CalendarApi } from '../../core/services/calendar-api';
import { CoursesApi } from '../../core/services/courses-api';
import { ReportsApi } from '../../core/services/reports-api';
import { extractDetail } from '../../shared/utils/api-error';
import { cycleLabel } from '../../shared/utils/cycles';
import { saveBlob } from '../../shared/utils/download';
import { weekdayLabel } from '../../shared/utils/weekdays';
import { PageHeader } from '../../shared/components/page-header/page-header';
import { UiAlert } from '../../shared/components/ui-alert/ui-alert';
import { UiButton } from '../../shared/components/ui-button/ui-button';

interface GroupCard {
  readonly group: Group;
  readonly blocks: ScheduleRow[];
}

@Component({
  selector: 'app-my-groups-page',
  imports: [DialogModule, PageHeader, UiAlert, UiButton],
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  templateUrl: './my-groups.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { class: 'block' },
})
export class MyGroupsPage {
  private readonly auth = inject(AuthService);
  private readonly courses = inject(CoursesApi);
  private readonly calendar = inject(CalendarApi);
  private readonly reports = inject(ReportsApi);
  private readonly toast = inject(MessageService);

  readonly cards = signal<GroupCard[]>([]);
  readonly semester = signal<string | null>(null);
  readonly loading = signal(true);
  readonly error = signal<string | null>(null);

  readonly selected = signal<Group | null>(null);
  readonly students = signal<EnrolledStudent[]>([]);
  readonly loadingStudents = signal(false);
  readonly downloading = signal<number | null>(null);
  studentsVisible = false;

  readonly totalStudents = computed(() =>
    this.cards().reduce((sum, card) => sum + card.group.enrolled_count, 0),
  );

  constructor() {
    this.load();
  }

  load(): void {
    const teacherId = this.auth.currentUser()?.id;
    this.loading.set(true);
    this.error.set(null);
    this.calendar.settings().subscribe({
      next: (settings) => {
        const semester = settings.semester_label;
        this.semester.set(semester);
        forkJoin({
          groups: this.courses.groups({ teacher_id: teacherId, semester }),
          schedule: this.courses.schedule({ teacher_id: teacherId, semester }),
        }).subscribe({
          next: ({ groups, schedule }) => {
            this.cards.set(
              groups.map((group) => ({
                group,
                blocks: schedule.filter((row) => row.group_id === group.id),
              })),
            );
            this.loading.set(false);
          },
          error: (err) => this.fail(err),
        });
      },
      error: (err) => this.fail(err),
    });
  }

  openStudents(group: Group): void {
    this.selected.set(group);
    this.students.set([]);
    this.studentsVisible = true;
    this.loadingStudents.set(true);
    this.courses.enrolled(group.id, false).subscribe({
      next: (students) => {
        this.students.set(students.filter((student) => !student.withdrawn_at));
        this.loadingStudents.set(false);
      },
      error: (err) => {
        this.loadingStudents.set(false);
        this.toast.add({ severity: 'error', summary: 'No se pudo cargar la lista', detail: extractDetail(err), life: 4000 });
      },
    });
  }

  downloadMatrix(group: Group): void {
    this.downloading.set(group.id);
    this.reports.groupMatrix(group.id).subscribe({
      next: (file) => {
        saveBlob(file.blob, file.filename);
        this.downloading.set(null);
      },
      error: (err) => {
        this.downloading.set(null);
        this.toast.add({ severity: 'error', summary: 'No se pudo generar el registro', detail: extractDetail(err), life: 4000 });
      },
    });
  }

  cycle(group: Group): string {
    return cycleLabel(group.cycle);
  }

  occupancy(group: Group): number {
    return group.capacity > 0 ? Math.min(100, Math.round((group.enrolled_count * 100) / group.capacity)) : 0;
  }

  day(weekday: number): string {
    return weekdayLabel(weekday);
  }

  hours(row: ScheduleRow): string {
    return `${row.start_time.slice(0, 5)}–${row.end_time.slice(0, 5)}`;
  }

  private fail(err: unknown): void {
    this.error.set(extractDetail(err));
    this.loading.set(false);
  }
}
