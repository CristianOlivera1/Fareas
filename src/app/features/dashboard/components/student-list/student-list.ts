import {
  ChangeDetectionStrategy,
  Component,
  CUSTOM_ELEMENTS_SCHEMA,
  DestroyRef,
  inject,
  signal,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { catchError, interval, map, of, startWith, switchMap } from 'rxjs';
import { Router } from '@angular/router';
import { DataTable } from '../../../../shared/components/data-table/data-table';
import { DataTableCellDirective } from '../../../../shared/components/data-table/data-table-cell.directive';
import { UiButton } from '../../../../shared/components/ui-button/ui-button';
import { TableColumn } from '../../../../core/models/table-column';
import { AttendanceToday } from '../../../../core/models/catalog';
import { AttendanceApi } from '../../../../core/services/attendance-api';

type StudentStatus = 'Asistió' | 'Tardanza' | 'Falta' | 'Falta justificada';

interface StudentRow {
  recordId: number;
  code: string;
  name: string;
  initials: string;
  status: StudentStatus;
  course: string;
  room: string;
  time: string;
}

const REFRESH_MS = 30_000;

const STATUS_DOT: Record<StudentStatus, string> = {
  Asistió: 'bg-green-500',
  Tardanza: 'bg-amber-500',
  Falta: 'bg-red-500',
  'Falta justificada': 'bg-blue-500',
};

function toRow(record: AttendanceToday): StudentRow {
  const status: StudentStatus =
    record.status === 'asistio'
      ? 'Asistió'
      : record.status === 'tardanza'
        ? 'Tardanza'
        : record.is_justified
          ? 'Falta justificada'
          : 'Falta';
  return {
    recordId: record.record_id,
    code: record.student_code ?? '—',
    name: record.student_name,
    initials: record.student_name
      .split(/\s+/)
      .filter(Boolean)
      .slice(0, 2)
      .map((part) => part[0]?.toUpperCase() ?? '')
      .join(''),
    status,
    course: record.course_name,
    room: record.room_code,
    time: record.marked_at && record.marked_at.length >= 16 ? record.marked_at.slice(11, 16) : '—',
  };
}

@Component({
  selector: 'app-student-list',
  imports: [DataTable, DataTableCellDirective, UiButton],
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  templateUrl: './student-list.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { class: 'block' },
})
export class StudentList {
  private readonly router = inject(Router);
  private readonly api = inject(AttendanceApi);
  private readonly destroyRef = inject(DestroyRef);

  readonly columns: TableColumn[] = [
    { id: 'index', header: 'N°', align: 'center', width: '3rem' },
    { id: 'code', header: 'Código' },
    { id: 'student', header: 'Estudiante' },
    { id: 'status', header: 'Estado' },
    { id: 'course', header: 'Curso', hiddenOnMobile: true },
    { id: 'room', header: 'Aula', align: 'center', hiddenOnMobile: true },
    { id: 'time', header: 'Hora' },
  ];

  readonly students = signal<StudentRow[]>([]);
  readonly loading = signal(true);
  readonly error = signal<string | null>(null);

  constructor() {
    interval(REFRESH_MS)
      .pipe(
        startWith(0),
        switchMap(() =>
          this.api.today().pipe(
            map((records) => ({ rows: records.map(toRow), failed: false })),
            catchError(() => of({ rows: null, failed: true })),
          ),
        ),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe(({ rows, failed }) => {
        if (rows) this.students.set(rows);
        this.error.set(failed ? 'No se pudo cargar la lista de asistencias.' : null);
        this.loading.set(false);
      });
  }

  trackByRecord(_index: number, row: unknown): unknown {
    return (row as StudentRow).recordId;
  }

  statusDot(status: StudentStatus): string {
    return STATUS_DOT[status];
  }

  goToAttendance(): void {
    void this.router.navigate(['/admin/attendance']);
  }
}
