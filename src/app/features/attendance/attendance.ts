import { ChangeDetectionStrategy, Component, CUSTOM_ELEMENTS_SCHEMA, computed, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Select } from 'primeng/select';
import { Tag } from 'primeng/tag';
import { DataTable } from '../../shared/components/data-table/data-table';
import { DataTableCellDirective } from '../../shared/components/data-table/data-table-cell.directive';
import { TableColumn } from '../../core/models/table-column';

/** Estados de asistencia según RF-23 (Tabla 8 del documento de requerimientos). */
type AttendanceStatus = 'Asistió' | 'Tardanza' | 'Falta';

interface AttendanceRecord {
  id: string;
  student: string;
  course: string;
  group: string;
  room: string;
  checkIn: string;
  method: 'Facial' | 'Manual';
  status: AttendanceStatus;
}

/** Datos de demostración coherentes con el horario de ejemplo del documento (RF). */
const MOCK_RECORDS: AttendanceRecord[] = [
  { id: 'R-001', student: 'Lucía Fernández Quispe', course: 'Inteligencia Artificial I', group: 'A', room: 'LAB 304', checkIn: '07:04', method: 'Facial', status: 'Asistió' },
  { id: 'R-002', student: 'Martín Gómez Ccahuana', course: 'Inteligencia Artificial I', group: 'A', room: 'LAB 304', checkIn: '07:22', method: 'Facial', status: 'Tardanza' },
  { id: 'R-003', student: 'Sofía Ruiz Huamán', course: 'Inteligencia Artificial I', group: 'A', room: 'LAB 304', checkIn: '07:01', method: 'Facial', status: 'Asistió' },
  { id: 'R-004', student: 'Diego Torres Mamani', course: 'Inteligencia Artificial I', group: 'A', room: 'LAB 304', checkIn: '-', method: 'Manual', status: 'Falta' },
  { id: 'R-005', student: 'Valentina Sosa Apaza', course: 'Computación Gráfica', group: 'B', room: 'LAB 401', checkIn: '07:06', method: 'Facial', status: 'Asistió' },
  { id: 'R-006', student: 'Pablo Núñez Condori', course: 'Computación Gráfica', group: 'B', room: 'LAB 401', checkIn: '07:26', method: 'Manual', status: 'Tardanza' },
  { id: 'R-007', student: 'Raul Montesinos Valdivia', course: 'Estructura de Datos', group: 'A', room: 'LAB 305', checkIn: '09:02', method: 'Facial', status: 'Asistió' },
  { id: 'R-008', student: 'Amelia Choque Rivas', course: 'Metodología Ágil', group: 'C', room: 'LAB 104', checkIn: '-', method: 'Manual', status: 'Falta' },
];

@Component({
  selector: 'app-attendance',
  imports: [FormsModule, Select, Tag, DataTable, DataTableCellDirective],
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  templateUrl: './attendance.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class Attendance {
  readonly query = signal('');
  readonly statusFilter = signal<'Todas' | AttendanceStatus>('Todas');
  readonly statusOptions = signal(['Todas', 'Asistió', 'Tardanza', 'Falta']);

  readonly columns: TableColumn[] = [
    { id: 'index', header: 'N°', align: 'center', width: '3.5rem' },
    { id: 'id', header: 'Registro' },
    { id: 'student', header: 'Estudiante' },
    { id: 'course', header: 'Curso', hiddenOnMobile: true },
    { id: 'group', header: 'Grupo', align: 'center' },
    { id: 'room', header: 'Aula', hiddenOnMobile: true },
    { id: 'checkIn', header: 'Ingreso' },
    { id: 'method', header: 'Método', hiddenOnMobile: true },
    { id: 'status', header: 'Estado', align: 'right' },
  ];

  readonly records = signal(MOCK_RECORDS);

  readonly filtered = computed(() => {
    const q = this.query().trim().toLowerCase();
    const status = this.statusFilter();
    return this.records().filter((r) => {
      const matchesQuery =
        !q ||
        r.student.toLowerCase().includes(q) ||
        r.id.toLowerCase().includes(q) ||
        r.course.toLowerCase().includes(q);
      const matchesStatus = status === 'Todas' || r.status === status;
      return matchesQuery && matchesStatus;
    });
  });

  trackById(_index: number, row: unknown): unknown {
    return (row as AttendanceRecord).id;
  }

  statusSeverity(status: AttendanceRecord['status']): 'success' | 'warn' | 'danger' {
    if (status === 'Asistió') return 'success';
    if (status === 'Tardanza') return 'warn';
    return 'danger';
  }

  clearFilters(): void {
    this.query.set('');
    this.statusFilter.set('Todas');
  }
}
