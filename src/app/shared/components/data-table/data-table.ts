import {
  ChangeDetectionStrategy,
  Component,
  CUSTOM_ELEMENTS_SCHEMA,
  computed,
  contentChildren,
  input,
  output,
  signal,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Select } from 'primeng/select';
import { TableColumn } from '../../../core/models/table-column';
import { DataTableCellDirective } from './data-table-cell.directive';

@Component({
  selector: 'app-data-table',
  imports: [CommonModule, FormsModule, Select],
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  templateUrl: './data-table.html',
  styleUrl: './data-table.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class DataTable {
  readonly columns = input.required<TableColumn[]>();
  readonly data = input.required<unknown[]>();
  readonly trackBy = input<(index: number, row: unknown) => unknown>((_, row) => row);

  readonly loading = input(false);
  readonly errorMessage = input<string | null>(null);
  readonly emptyTitle = input('Sin resultados');
  readonly emptyMessage = input('No hay datos para mostrar con los filtros actuales.');
  readonly emptyIcon = input('material-symbols:inbox-outline');
  readonly showClearFilters = input(false);

  readonly pageSizeOptions = input<Array<{ label: string; value: number }>>([
    { label: '5', value: 5 },
    { label: '10', value: 10 },
    { label: '25', value: 25 },
  ]);

  readonly retry = output<void>();
  readonly clearFilters = output<void>();

  readonly cellTemplates = contentChildren(DataTableCellDirective);

  private readonly page = signal(1);
  readonly perPage = signal(5);

  readonly totalCount = computed(() => this.data().length);
  readonly totalPages = computed(() => Math.max(1, Math.ceil(this.totalCount() / this.perPage())));
  readonly currentPage = computed(() => Math.min(this.page(), this.totalPages()));

  readonly pagedData = computed(() => {
    const start = (this.currentPage() - 1) * this.perPage();
    return this.data().slice(start, start + this.perPage());
  });

  readonly visiblePages = computed(() => {
    const total = this.totalPages();
    const current = this.currentPage();
    if (total <= 7) return Array.from({ length: total }, (_, i) => i + 1);
    if (current <= 4) return [1, 2, 3, 4, 5];
    if (current >= total - 3) return [total - 4, total - 3, total - 2, total - 1, total];
    return [current - 2, current - 1, current, current + 1, current + 2];
  });

  getCellTemplate(columnId: string): DataTableCellDirective | undefined {
    return this.cellTemplates().find((t) => t.appCell() === columnId);
  }

  rowNumber(rowIndex: number): number {
    return (this.currentPage() - 1) * this.perPage() + rowIndex + 1;
  }

  onPage(page: number): void {
    this.page.set(page);
  }

  onPerPage(value: number): void {
    this.perPage.set(value);
    this.page.set(1);
  }
}
