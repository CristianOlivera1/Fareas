import { ChangeDetectionStrategy, Component, CUSTOM_ELEMENTS_SCHEMA, computed, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Select } from 'primeng/select';
import { Tag } from 'primeng/tag';
import { DataTable } from '../../shared/components/data-table/data-table';
import { DataTableCellDirective } from '../../shared/components/data-table/data-table-cell.directive';
import { TableColumn } from '../../core/models/table-column';

interface AttendanceRecord {
  id: string;
  employee: string;
  area: string;
  checkIn: string;
  method: 'Facial' | 'Manual';
  status: 'Presente' | 'Tarde' | 'Ausente';
}

const MOCK_RECORDS: AttendanceRecord[] = [
  { id: 'A-101', employee: 'Lucía Fernández', area: 'Ventas', checkIn: '08:02', method: 'Facial', status: 'Presente' },
  { id: 'A-102', employee: 'Martín Gómez', area: 'Soporte', checkIn: '08:17', method: 'Facial', status: 'Tarde' },
  { id: 'A-103', employee: 'Sofía Ruiz', area: 'RR.HH.', checkIn: '08:01', method: 'Facial', status: 'Presente' },
  { id: 'A-104', employee: 'Diego Torres', area: 'Logística', checkIn: '—', method: 'Manual', status: 'Ausente' },
  { id: 'A-105', employee: 'Valentina Sosa', area: 'Ventas', checkIn: '08:05', method: 'Facial', status: 'Presente' },
  { id: 'A-106', employee: 'Pablo Núñez', area: 'IT', checkIn: '08:22', method: 'Manual', status: 'Tarde' },
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
  readonly statusFilter = signal<'Todas' | AttendanceRecord['status']>('Todas');
  readonly statusOptions = signal(['Todas', 'Presente', 'Tarde', 'Ausente']);

  readonly columns: TableColumn[] = [
    { id: 'index', header: 'N°', align: 'center', width: '3.5rem' },
    { id: 'id', header: 'ID' },
    { id: 'employee', header: 'Empleado' },
    { id: 'area', header: 'Área', hiddenOnMobile: true },
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
        r.employee.toLowerCase().includes(q) ||
        r.id.toLowerCase().includes(q) ||
        r.area.toLowerCase().includes(q);
      const matchesStatus = status === 'Todas' || r.status === status;
      return matchesQuery && matchesStatus;
    });
  });

  trackById(_index: number, row: unknown): unknown {
    return (row as AttendanceRecord).id;
  }

  statusSeverity(status: AttendanceRecord['status']): 'success' | 'warn' | 'danger' {
    if (status === 'Presente') return 'success';
    if (status === 'Tarde') return 'warn';
    return 'danger';
  }

  clearFilters(): void {
    this.query.set('');
    this.statusFilter.set('Todas');
  }
}
