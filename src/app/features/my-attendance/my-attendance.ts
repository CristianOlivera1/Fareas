import {
  ChangeDetectionStrategy,
  Component,
  CUSTOM_ELEMENTS_SCHEMA,
  computed,
  inject,
  signal,
} from '@angular/core';
import { TagModule } from 'primeng/tag';
import { forkJoin } from 'rxjs';

import { AttendanceApi, MyAttendance, MyDpi } from '../../core/services/attendance-api';
import { TableColumn } from '../../core/models/table-column';
import { extractDetail } from '../../shared/utils/api-error';
import { PageHeader } from '../../shared/components/page-header/page-header';
import { UiButton } from '../../shared/components/ui-button/ui-button';
import { UiAlert } from '../../shared/components/ui-alert/ui-alert';
import { DataTable } from '../../shared/components/data-table/data-table';
import { DataTableCellDirective } from '../../shared/components/data-table/data-table-cell.directive';

type RecordLabel = 'Asistió' | 'Tardanza' | 'Falta' | 'Falta justificada';
type Severity = 'success' | 'warn' | 'danger' | 'info';
type DpiLevel = 'ok' | 'alerta' | 'limite';

const RECORD_SEVERITY: Record<RecordLabel, Severity> = {
  'Asistió': 'success',
  'Tardanza': 'warn',
  'Falta': 'danger',
  'Falta justificada': 'info',
};

const DPI_STYLES: Record<DpiLevel, { bar: string; text: string; label: string }> = {
  ok: { bar: 'bg-green-500', text: 'text-green-700', label: 'En regla' },
  alerta: { bar: 'bg-amber-500', text: 'text-amber-700', label: 'En riesgo' },
  limite: { bar: 'bg-red-500', text: 'text-red-700', label: 'Límite superado' },
};

@Component({
  selector: 'app-my-attendance-page',
  imports: [PageHeader, UiButton, UiAlert, DataTable, DataTableCellDirective, TagModule],
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  templateUrl: './my-attendance.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { class: 'block' },
})
export class MyAttendancePage {
  private readonly api = inject(AttendanceApi);

  readonly records = signal<MyAttendance[]>([]);
  readonly dpi = signal<MyDpi[]>([]);
  readonly loading = signal(true);
  readonly error = signal<string | null>(null);
  readonly from = signal('');
  readonly to = signal('');

  readonly hasFilters = computed(() => this.from() !== '' || this.to() !== '');

  readonly columns: TableColumn[] = [
    { id: 'session_date', header: 'Fecha' },
    { id: 'course_code', header: 'Curso' },
    { id: 'group_code', header: 'Grupo', hiddenOnMobile: true },
    { id: 'schedule', header: 'Horario', hiddenOnMobile: true },
    { id: 'status', header: 'Estado' },
    { id: 'method', header: 'Método', hiddenOnMobile: true },
    { id: 'correct_reason', header: 'Rectificación', hiddenOnMobile: true },
  ];

  readonly trackById = (_: number, row: unknown) => (row as MyAttendance).record_id;

  constructor() {
    this.load();
  }

  load(): void {
    this.loading.set(true);
    this.error.set(null);
    forkJoin({
      records: this.api.mine({ desde: this.from(), hasta: this.to() }),
      dpi: this.api.myDpi(),
    }).subscribe({
      next: ({ records, dpi }) => {
        this.records.set(records);
        this.dpi.set(dpi);
        this.loading.set(false);
      },
      error: (err) => {
        this.error.set(extractDetail(err));
        this.loading.set(false);
      },
    });
  }

  setFrom(value: string): void {
    this.from.set(value);
    this.load();
  }

  setTo(value: string): void {
    this.to.set(value);
    this.load();
  }

  clearFilters(): void {
    this.from.set('');
    this.to.set('');
    this.load();
  }

  label(record: MyAttendance): RecordLabel {
    if (record.status === 'asistio') return 'Asistió';
    if (record.status === 'tardanza') return 'Tardanza';
    return record.is_justified ? 'Falta justificada' : 'Falta';
  }

  severity(record: MyAttendance): Severity {
    return RECORD_SEVERITY[this.label(record)];
  }

  style(item: MyDpi) {
    return DPI_STYLES[item.nivel ?? 'ok'];
  }

  barWidth(item: MyDpi): number {
    return Math.min(100, Math.max(0, item.absence_percent));
  }

  schedule(record: MyAttendance): string {
    return `${record.start_time}–${record.end_time}`;
  }
}
