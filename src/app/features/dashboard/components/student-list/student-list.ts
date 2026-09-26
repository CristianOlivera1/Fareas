import {
  ChangeDetectionStrategy,
  Component,
  CUSTOM_ELEMENTS_SCHEMA,
  inject,
  signal,
} from '@angular/core';
import { Router } from '@angular/router';
import { DataTable } from '../../../../shared/components/data-table/data-table';
import { DataTableCellDirective } from '../../../../shared/components/data-table/data-table-cell.directive';
import { UiButton } from '../../../../shared/components/ui-button/ui-button';
import { TableColumn } from '../../../../core/models/table-column';

type StudentStatus = 'Asistió' | 'Tarde' | 'Sin registro' | 'Falta';

interface StudentRow {
  code: string;
  name: string;
  initials: string;
  status: StudentStatus;
  course: string;
  room: string;
  time: string;
}

const MOCK_STUDENTS: StudentRow[] = [
  { code: '221155', name: 'Raul Montesinos', initials: 'RM', status: 'Asistió', course: 'Base de datos I', room: '305', time: '11:15 am' },
  { code: '25511', name: 'Razib Rahman', initials: 'RR', status: 'Tarde', course: 'Metodología ágil', room: '104', time: '9:15 am' },
  { code: '24447', name: 'Luke Norton', initials: 'LN', status: 'Asistió', course: 'Big data', room: '202', time: '9:00 am' },
  { code: '221181', name: 'Lucía Fernández', initials: 'LF', status: 'Asistió', course: 'Estructura de datos', room: '305', time: '8:02 am' },
  { code: '31002', name: 'Diego Torres', initials: 'DT', status: 'Falta', course: 'Redes I', room: '410', time: '—' },
  { code: '18734', name: 'Valentina Sosa', initials: 'VS', status: 'Sin registro', course: 'Big data', room: '202', time: '—' },
];

const STATUS_DOT: Record<StudentStatus, string> = {
  Asistió: 'bg-green-500',
  Tarde: 'bg-amber-500',
  'Sin registro': 'bg-gray-400',
  Falta: 'bg-red-500',
};

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

  readonly columns: TableColumn[] = [
    { id: 'index', header: 'N°', align: 'center', width: '3rem' },
    { id: 'code', header: 'Código' },
    { id: 'student', header: 'Estudiante' },
    { id: 'status', header: 'Estado' },
    { id: 'course', header: 'Curso', hiddenOnMobile: true },
    { id: 'room', header: 'Aula', align: 'center', hiddenOnMobile: true },
    { id: 'time', header: 'Hora' },
    { id: 'actions', header: 'Acciones', align: 'right' },
  ];

  readonly students = signal(MOCK_STUDENTS);

  trackByCode(_index: number, row: unknown): unknown {
    return (row as StudentRow).code;
  }

  statusDot(status: StudentStatus): string {
    return STATUS_DOT[status];
  }

  goToAttendance(): void {
    void this.router.navigate(['/admin/attendance']);
  }
}
