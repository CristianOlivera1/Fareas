import {
  ChangeDetectionStrategy,
  Component,
  CUSTOM_ELEMENTS_SCHEMA,
  computed,
  effect,
  inject,
  signal,
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import { JsonPipe } from '@angular/common';
import { DialogModule } from 'primeng/dialog';
import { SelectModule } from 'primeng/select';

import { AuditApi, AuditEntry } from '../../core/services/audit-api';
import { TableColumn } from '../../core/models/table-column';
import { extractDetail } from '../../shared/utils/api-error';
import { QueryParams } from '../../shared/utils/query-params';
import { PageHeader } from '../../shared/components/page-header/page-header';
import { UiButton } from '../../shared/components/ui-button/ui-button';
import { UiAlert } from '../../shared/components/ui-alert/ui-alert';
import { DataTable } from '../../shared/components/data-table/data-table';
import { DataTableCellDirective } from '../../shared/components/data-table/data-table-cell.directive';

const ROLE_LABELS: Record<string, string> = {
  admin: 'Administrador',
  docente: 'Docente',
  estudiante: 'Estudiante',
};

const ROLE_OPTIONS = [
  { label: 'Todos los roles', value: null },
  { label: 'Administrador', value: 'admin' },
  { label: 'Docente', value: 'docente' },
  { label: 'Estudiante', value: 'estudiante' },
];

@Component({
  selector: 'app-audit-page',
  imports: [
    FormsModule,
    JsonPipe,
    DialogModule,
    SelectModule,
    PageHeader,
    UiButton,
    UiAlert,
    DataTable,
    DataTableCellDirective,
  ],
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  templateUrl: './audit.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { class: 'block' },
})
export class AuditPage {
  private readonly api = inject(AuditApi);
  private readonly qp = inject(QueryParams);

  readonly roleOptions = ROLE_OPTIONS;

  readonly columns: TableColumn[] = [
    { id: 'created_at', header: 'Fecha' },
    { id: 'actor', header: 'Quién' },
    { id: 'action', header: 'Acción' },
    { id: 'entity', header: 'Entidad', hiddenOnMobile: true },
    { id: 'ip_address', header: 'IP', hiddenOnMobile: true },
    { id: 'detail', header: 'Detalle', align: 'center', width: '80px' },
  ];

  readonly action = this.qp.filter('action');
  readonly entity = this.qp.filter('entity');
  readonly role = this.qp.filter('actor_role');
  readonly since = this.qp.filter('since');
  readonly page = this.qp.number('page', 1);
  readonly pageSize = this.qp.number('page_size', 10);

  readonly entries = signal<AuditEntry[]>([]);
  readonly total = signal(0);
  readonly loading = signal(false);
  readonly error = signal<string | null>(null);
  readonly selected = signal<AuditEntry | null>(null);
  detailVisible = false;

  readonly hasFilters = computed(
    () => !!(this.action() || this.entity() || this.role() || this.since()),
  );

  constructor() {
    effect(() => {
      this.action();
      this.entity();
      this.role();
      this.since();
      this.page();
      this.pageSize();
      this.load();
    });
  }

  roleLabel(role: string | null): string {
    return role ? (ROLE_LABELS[role] ?? role) : 'Sistema';
  }

  formatDate(value: string | null): string {
    return value ? value.replace('T', ' ') : '—';
  }

  trackById(_: number, row: unknown): unknown {
    return (row as AuditEntry).id;
  }

  setFilter(name: 'action' | 'entity' | 'actor_role' | 'since', value: string | null): void {
    void this.qp.update({ [name]: value?.trim() || null, page: null });
  }

  clearFilters(): void {
    void this.qp.update({ action: null, entity: null, actor_role: null, since: null, page: null });
  }

  onPage(page: number): void {
    void this.qp.update({ page });
  }

  onPageSize(size: number): void {
    void this.qp.update({ page_size: size, page: null });
  }

  reload(): void {
    this.load();
  }

  openDetail(entry: AuditEntry): void {
    this.selected.set(entry);
    this.detailVisible = true;
  }

  private load(): void {
    this.loading.set(true);
    this.error.set(null);
    const since = this.since();
    this.api
      .list({
        page: this.page(),
        page_size: this.pageSize(),
        action: this.action(),
        entity: this.entity(),
        actor_role: this.role(),
        since: since ? `${since}T00:00:00` : null,
      })
      .subscribe({
        next: (result) => {
          this.entries.set(result.items);
          this.total.set(result.total);
          this.loading.set(false);
        },
        error: (err) => {
          this.error.set(extractDetail(err));
          this.loading.set(false);
        },
      });
  }
}
