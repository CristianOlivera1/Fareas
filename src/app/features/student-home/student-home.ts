import {
  ChangeDetectionStrategy,
  Component,
  CUSTOM_ELEMENTS_SCHEMA,
  computed,
  inject,
  signal,
} from '@angular/core';
import { RouterLink } from '@angular/router';
import { forkJoin } from 'rxjs';

import { ADMIN_PREFIX } from '../../core/constants/nav';
import { ScheduleRow } from '../../core/models/catalog';
import { AuthService } from '../../core/services/auth/auth';
import { AttendanceApi, MyAttendance, MyDpi } from '../../core/services/attendance-api';
import { StudentPortalApi } from '../../core/services/student-portal-api';
import { extractDetail } from '../../shared/utils/api-error';
import { PageHeader } from '../../shared/components/page-header/page-header';
import { UiAlert } from '../../shared/components/ui-alert/ui-alert';

type ClassState = 'done' | 'now' | 'next';

interface TodayClass {
  readonly row: ScheduleRow;
  readonly state: ClassState;
}

const STATE_STYLES: Record<ClassState, { label: string; chip: string }> = {
  done: { label: 'Finalizada', chip: 'bg-gray-100 text-gray-500' },
  now: { label: 'En curso', chip: 'bg-green-50 text-green-700' },
  next: { label: 'Pendiente', chip: 'bg-blue-50 text-(--fareas-primary)' },
};

const STATUS_LABELS = {
  asistio: { label: 'Asistió', dot: 'bg-green-500' },
  tardanza: { label: 'Tardanza', dot: 'bg-amber-500' },
  falta: { label: 'Falta', dot: 'bg-red-500' },
  justified: { label: 'Falta justificada', dot: 'bg-blue-500' },
} as const;

const RECENT_RECORDS = 5;

function isoWeekday(date: Date): number {
  return date.getDay() === 0 ? 7 : date.getDay();
}

function minutesOf(time: string): number {
  return Number(time.slice(0, 2)) * 60 + Number(time.slice(3, 5));
}

@Component({
  selector: 'app-student-home-page',
  imports: [RouterLink, PageHeader, UiAlert],
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  templateUrl: './student-home.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { class: 'block' },
})
export class StudentHomePage {
  private readonly portal = inject(StudentPortalApi);
  private readonly attendance = inject(AttendanceApi);
  private readonly auth = inject(AuthService);

  protected readonly prefix = ADMIN_PREFIX;

  readonly schedule = signal<ScheduleRow[]>([]);
  readonly dpi = signal<MyDpi[]>([]);
  readonly records = signal<MyAttendance[]>([]);
  readonly loading = signal(true);
  readonly error = signal<string | null>(null);
  private readonly now = signal(new Date());

  readonly firstName = computed(() => {
    const name = this.auth.currentUser()?.full_name ?? '';
    return name.split(/\s+/)[0] ?? '';
  });

  readonly todayLabel = computed(() =>
    this.now().toLocaleDateString('es-PE', { weekday: 'long', day: 'numeric', month: 'long' }),
  );

  readonly todayClasses = computed<TodayClass[]>(() => {
    const now = this.now();
    const minutes = now.getHours() * 60 + now.getMinutes();
    const weekday = isoWeekday(now);
    return this.schedule()
      .filter((row) => row.weekday === weekday)
      .sort((a, b) => a.start_time.localeCompare(b.start_time))
      .map((row) => ({
        row,
        state:
          minutes >= minutesOf(row.end_time)
            ? 'done'
            : minutes >= minutesOf(row.start_time)
              ? 'now'
              : 'next',
      }));
  });

  readonly atRisk = computed(() =>
    this.dpi()
      .filter((item) => item.nivel !== null)
      .sort((a, b) => b.absence_percent - a.absence_percent),
  );

  readonly recent = computed(() => this.records().slice(0, RECENT_RECORDS));

  constructor() {
    forkJoin({
      schedule: this.portal.schedule(),
      dpi: this.attendance.myDpi(),
      records: this.attendance.mine(),
    }).subscribe({
      next: ({ schedule, dpi, records }) => {
        this.schedule.set(schedule);
        this.dpi.set(dpi);
        this.records.set(records);
        this.loading.set(false);
      },
      error: (err) => {
        this.error.set(extractDetail(err));
        this.loading.set(false);
      },
    });
  }

  stateStyle(state: ClassState) {
    return STATE_STYLES[state];
  }

  hours(row: ScheduleRow): string {
    return `${row.start_time.slice(0, 5)}–${row.end_time.slice(0, 5)}`;
  }

  recordStyle(record: MyAttendance) {
    if (record.status === 'falta' && record.is_justified) return STATUS_LABELS.justified;
    return STATUS_LABELS[record.status];
  }
}
