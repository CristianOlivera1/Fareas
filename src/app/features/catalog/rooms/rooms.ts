import {
  ChangeDetectionStrategy,
  Component,
  CUSTOM_ELEMENTS_SCHEMA,
  effect,
  inject,
  signal,
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MessageService } from 'primeng/api';
import { DialogModule } from 'primeng/dialog';
import { InputTextModule } from 'primeng/inputtext';
import { ToggleSwitchModule } from 'primeng/toggleswitch';

import { QueryParams } from '../../../shared/utils/query-params';
import { CatalogApi } from '../../../core/services/catalog-api';
import { AuthService } from '../../../core/services/auth/auth';
import { PageHeader } from '../../../shared/components/page-header/page-header';
import { UiButton } from '../../../shared/components/ui-button/ui-button';
import { UiInput } from '../../../shared/components/ui-input/ui-input';
import { UiAlert } from '../../../shared/components/ui-alert/ui-alert';
import { DataTable } from '../../../shared/components/data-table/data-table';
import { DataTableCellDirective } from '../../../shared/components/data-table/data-table-cell.directive';
import { TableColumn } from '../../../core/models/table-column';
import { Room } from '../../../core/models/catalog';

/** Extrae el 'detail' del error de FastAPI (o cae a un mensaje genérico).
 * La exportan las demás pantallas del catálogo. */
export function extractDetail(err: unknown): string {
  const anyErr = err as { error?: { detail?: string }; message?: string };
  return anyErr?.error?.detail ?? anyErr?.message ?? 'Error de conexión con el servidor';
}

interface RoomForm {
  id: number | null;
  code: string;
  name: string;
  building: string;
  is_active: boolean;
}

@Component({
  selector: 'app-rooms-page',
  imports: [
    FormsModule,
    PageHeader,
    UiButton,
    UiInput,
    UiAlert,
    DataTable,
    DataTableCellDirective,
    DialogModule,
    InputTextModule,
    ToggleSwitchModule,
  ],
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  templateUrl: './rooms.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class RoomsPage {
  protected readonly auth = inject(AuthService);
  private readonly api = inject(CatalogApi);
  private readonly qp = inject(QueryParams);
  private readonly toast = inject(MessageService);

  readonly columns: TableColumn[] = [
    { id: 'index', header: 'N°', width: '60px', align: 'center' },
    { id: 'code', header: 'Código' },
    { id: 'name', header: 'Nombre' },
    { id: 'building', header: 'Edificio', hiddenOnMobile: true },
    { id: 'is_active', header: 'Estado', align: 'center' },
    { id: 'actions', header: 'Acciones', align: 'center', width: '90px' },
  ];

  readonly q = this.qp.filter('q');
  readonly page = this.qp.number('page', 1);
  readonly pageSize = this.qp.number('page_size', 10);

  readonly rooms = signal<Room[]>([]);
  readonly total = signal(0);
  readonly loading = signal(false);
  readonly error = signal<string | null>(null);
  readonly saving = signal(false);

  readonly form = signal<RoomForm>({ id: null, code: '', name: '', building: '', is_active: true });

  dialogVisible = false;

  constructor() {
    // carga inicial + reacción a cambios de URL (filtros/paginación)
    effect(() => {
      this.q();
      this.page();
      this.pageSize();
      void this.load();
    });
  }

  patch(patch: Partial<RoomForm>): void {
    this.form.update((f) => ({ ...f, ...patch }));
  }

  onSearch(value: string): void {
    void this.qp.update({ q: value || null, page: null });
  }

  onPage(p: number): void {
    void this.qp.update({ page: p });
  }

  onPageSize(size: number): void {
    void this.qp.update({ page_size: size, page: null });
  }

  reload(): void {
    void this.load();
  }

  openCreate(): void {
    this.form.set({ id: null, code: '', name: '', building: '', is_active: true });
    this.dialogVisible = true;
  }

  openEdit(room: Room): void {
    this.form.set({
      id: room.id,
      code: room.code,
      name: room.name ?? '',
      building: room.building ?? '',
      is_active: room.is_active,
    });
    this.dialogVisible = true;
  }

  async save(): Promise<void> {
    const f = this.form();
    if (f.id === null && f.code.trim().length < 1) {
      this.toast.add({ severity: 'warn', summary: 'Falta el código', life: 2500 });
      return;
    }
    this.saving.set(true);
    try {
      if (f.id === null) {
        await this.api
          .createRoom({ code: f.code.trim(), name: f.name, building: f.building })
          .toPromise();
        this.toast.add({ severity: 'success', summary: 'Aula creada', life: 2500 });
      } else {
        await this.api
          .updateRoom(f.id, { name: f.name, building: f.building, is_active: f.is_active })
          .toPromise();
        this.toast.add({ severity: 'success', summary: 'Aula actualizada', life: 2500 });
      }
      this.dialogVisible = false;
      void this.load();
    } catch (err) {
      this.toast.add({
        severity: 'error',
        summary: 'No se pudo guardar',
        detail: extractDetail(err),
        life: 4000,
      });
    } finally {
      this.saving.set(false);
    }
  }

  private async load(): Promise<void> {
    this.loading.set(true);
    this.error.set(null);
    try {
      const res = await this.api
        .rooms({ page: this.page(), page_size: this.pageSize(), q: this.q() })
        .toPromise();
      this.rooms.set(res?.items ?? []);
      this.total.set(res?.total ?? 0);
    } catch (err) {
      this.error.set(extractDetail(err));
    } finally {
      this.loading.set(false);
    }
  }
}
