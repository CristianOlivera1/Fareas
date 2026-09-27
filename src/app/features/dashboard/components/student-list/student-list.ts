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

/**
 * Estados en el panel: Asistió/Tardanza/Falta según RF-23.
 * "Sin registro" es un estado transitorio de vista: la sesión del curso
 * sigue abierta, por lo que aún no puede clasificarse como Falta (RF-26).
 */
type StudentStatus = 'Asistió' | 'Tardanza' | 'Sin registro' | 'Falta';

interface StudentRow {
  code: string;
  name: string;
  initials: string;
  status: StudentStatus;
  course: string;
  room: string;
  time: string;
}

/** Datos de demostración coherentes con el activity-feed y la página de asistencias. */
const MOCK_STUDENTS: StudentRow[] = [
  { code: '221181', name: 'Raul Montesinos Valdivia', initials: 'RM', status: 'Asistió', course: 'Metodología de la Investigación Científica', room: 'LAB 305', time: '9:02 am' },
  { code: '231204', name: 'Razib Rahman Ttito', initials: 'RT', status: 'Tardanza', course: 'Metodología de la Investigación Científica', room: 'LAB 305', time: '9:18 am' },
  { code: '221105', name: 'Lucía Fernández Quispe', initials: 'LF', status: 'Asistió', course: 'Metodología de la Investigación Científica', room: 'LAB 305', time: '9:01 am' },
  { code: '222046', name: 'Valentina Sosa Apaza', initials: 'VS', status: 'Asistió', course: 'Sistemas Distribuidos', room: 'LAB 304', time: '9:00 am' },
  { code: '223014', name: 'Diego Torres Mamani', initials: 'DT', status: 'Falta', course: 'Sistemas Distribuidos', room: 'LAB 304', time: '-' },
  { code: '231150', name: 'Luis Navarro Cusihuaranga', initials: 'LN', status: 'Sin registro', course: 'Sistemas Distribuidos', room: 'LAB 304', time: '-' },
];

const STATUS_DOT: Record<StudentStatus, string> = {
  Asistió: 'bg-green-500',
  Tardanza: 'bg-amber-500',
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
