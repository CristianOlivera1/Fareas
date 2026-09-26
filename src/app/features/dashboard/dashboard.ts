import { ChangeDetectionStrategy, Component, CUSTOM_ELEMENTS_SCHEMA, computed, signal } from '@angular/core';
import { Tag } from 'primeng/tag';
import { DataTable } from '../../shared/components/data-table/data-table';
import { DataTableCellDirective } from '../../shared/components/data-table/data-table-cell.directive';
import { TableColumn } from '../../core/models/table-column';

interface StatCard {
  title: string;
  value: string;
  detail: string;
  icon: string;
  accent: string;
}

interface AttendanceRow {
  name: string;
  time: string;
  status: 'Presente' | 'Tarde' | 'Ausente';
}

@Component({
  selector: 'app-dashboard',
  imports: [Tag, DataTable, DataTableCellDirective],
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  templateUrl: './dashboard.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class Dashboard {
  readonly cards = signal<StatCard[]>([
    {
      title: 'Asistencias hoy',
      value: '128',
      detail: '12 tardanzas',
      icon: 'material-symbols:fact-check-outline',
      accent: 'text-green-600',
    },
    {
      title: 'Empleados activos',
      value: '142',
      detail: '3 de licencia',
      icon: 'material-symbols:group-outline',
      accent: 'text-(--fareas-primary)',
    },
    {
      title: 'Ausencias',
      value: '11',
      detail: '7.7% del plantel',
      icon: 'material-symbols:person-off-outline',
      accent: 'text-red-500',
    },
    {
      title: 'Reconocimiento facial',
      value: '98.2%',
      detail: 'precisión mock',
      icon: 'material-symbols:face-outline',
      accent: 'text-amber-600',
    },
  ]);

  readonly columns: TableColumn[] = [
    { id: 'index', header: 'N°', align: 'center', width: '3.5rem' },
    { id: 'name', header: 'Empleado' },
    { id: 'time', header: 'Hora' },
    { id: 'status', header: 'Estado', align: 'right' },
  ];

  readonly latest = signal<AttendanceRow[]>([
    { name: 'Lucía Fernández', time: '08:02', status: 'Presente' },
    { name: 'Martín Gómez', time: '08:17', status: 'Tarde' },
    { name: 'Sofía Ruiz', time: '08:01', status: 'Presente' },
    { name: 'Diego Torres', time: '—', status: 'Ausente' },
    { name: 'Valentina Sosa', time: '08:05', status: 'Presente' },
  ]);

  readonly presentCount = computed(() => this.latest().filter((r) => r.status === 'Presente').length);

  trackByName(_index: number, row: unknown): unknown {
    return (row as AttendanceRow).name;
  }

  statusSeverity(status: AttendanceRow['status']): 'success' | 'warn' | 'danger' {
    if (status === 'Presente') return 'success';
    if (status === 'Tarde') return 'warn';
    return 'danger';
  }
}
