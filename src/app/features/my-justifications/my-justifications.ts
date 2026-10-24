import {
  ChangeDetectionStrategy,
  Component,
  CUSTOM_ELEMENTS_SCHEMA,
  inject,
  signal,
} from '@angular/core';

import { MyJustification, StudentPortalApi } from '../../core/services/student-portal-api';
import { TableColumn } from '../../core/models/table-column';
import { extractDetail } from '../../shared/utils/api-error';
import { PageHeader } from '../../shared/components/page-header/page-header';
import { UiAlert } from '../../shared/components/ui-alert/ui-alert';
import { UiButton } from '../../shared/components/ui-button/ui-button';
import { DataTable } from '../../shared/components/data-table/data-table';
import { DataTableCellDirective } from '../../shared/components/data-table/data-table-cell.directive';

@Component({
  selector: 'app-my-justifications-page',
  imports: [PageHeader, UiAlert, UiButton, DataTable, DataTableCellDirective],
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  templateUrl: './my-justifications.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { class: 'block' },
})
export class MyJustificationsPage {
  private readonly portal = inject(StudentPortalApi);

  readonly columns: TableColumn[] = [
    { id: 'range', header: 'Fechas' },
    { id: 'course_code', header: 'Curso' },
    { id: 'reason', header: 'Motivo' },
    { id: 'created_by_name', header: 'Registrada por', hiddenOnMobile: true },
    { id: 'document', header: 'Documento', align: 'center' },
  ];

  readonly items = signal<MyJustification[]>([]);
  readonly loading = signal(true);
  readonly error = signal<string | null>(null);

  constructor() {
    this.load();
  }

  load(): void {
    this.loading.set(true);
    this.error.set(null);
    this.portal.justifications().subscribe({
      next: (items) => {
        this.items.set(items);
        this.loading.set(false);
      },
      error: (err) => {
        this.error.set(extractDetail(err));
        this.loading.set(false);
      },
    });
  }

  trackById(_: number, row: unknown): unknown {
    return (row as MyJustification).id;
  }

  range(item: MyJustification): string {
    return item.start_date === item.end_date ? item.start_date : `${item.start_date} → ${item.end_date}`;
  }
}
