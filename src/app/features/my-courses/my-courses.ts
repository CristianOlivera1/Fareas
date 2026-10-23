import {
  ChangeDetectionStrategy,
  Component,
  CUSTOM_ELEMENTS_SCHEMA,
  computed,
  inject,
  signal,
} from '@angular/core';
import { forkJoin } from 'rxjs';

import { AttendanceApi, MyDpi } from '../../core/services/attendance-api';
import { MyCourse, StudentPortalApi } from '../../core/services/student-portal-api';
import { extractDetail } from '../../shared/utils/api-error';
import { cycleLabel } from '../../shared/utils/cycles';
import { weekdayLabel } from '../../shared/utils/weekdays';
import { PageHeader } from '../../shared/components/page-header/page-header';
import { UiAlert } from '../../shared/components/ui-alert/ui-alert';
import { UiButton } from '../../shared/components/ui-button/ui-button';

interface CourseCard {
  readonly course: MyCourse;
  readonly dpi: MyDpi | null;
}

const LEVEL_STYLES = {
  ok: { bar: 'bg-green-500', text: 'text-green-700', label: 'En regla' },
  alerta: { bar: 'bg-amber-500', text: 'text-amber-700', label: 'En riesgo' },
  limite: { bar: 'bg-red-500', text: 'text-red-700', label: 'Límite superado' },
} as const;

@Component({
  selector: 'app-my-courses-page',
  imports: [PageHeader, UiAlert, UiButton],
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  templateUrl: './my-courses.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { class: 'block' },
})
export class MyCoursesPage {
  private readonly portal = inject(StudentPortalApi);
  private readonly attendance = inject(AttendanceApi);

  readonly cards = signal<CourseCard[]>([]);
  readonly loading = signal(true);
  readonly error = signal<string | null>(null);

  readonly semester = computed(() => this.cards()[0]?.course.semester_label ?? null);

  constructor() {
    this.load();
  }

  load(): void {
    this.loading.set(true);
    this.error.set(null);
    forkJoin({ courses: this.portal.courses(), dpi: this.attendance.myDpi() }).subscribe({
      next: ({ courses, dpi }) => {
        const byCourse = new Map(dpi.map((item) => [item.course_id, item]));
        this.cards.set(
          courses.map((course) => ({ course, dpi: byCourse.get(course.course_id) ?? null })),
        );
        this.loading.set(false);
      },
      error: (err) => {
        this.error.set(extractDetail(err));
        this.loading.set(false);
      },
    });
  }

  cycle(course: MyCourse): string {
    return cycleLabel(course.cycle);
  }

  day(weekday: number): string {
    return weekdayLabel(weekday);
  }

  hours(start: string, end: string): string {
    return `${start.slice(0, 5)}–${end.slice(0, 5)}`;
  }

  style(dpi: MyDpi) {
    return LEVEL_STYLES[dpi.nivel ?? 'ok'];
  }

  barWidth(dpi: MyDpi): number {
    return Math.min(100, Math.max(0, dpi.absence_percent));
  }
}
