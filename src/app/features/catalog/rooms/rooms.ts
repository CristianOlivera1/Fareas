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
import { QueryParams } from '../../../shared/utils/query-params';
import { extractDetail } from '../../../shared/utils/api-error';
import { CatalogApi } from '../../../core/services/catalog-api';
import { AuthService } from '../../../core/services/auth/auth';
import { PageHeader } from '../../../shared/components/page-header/page-header';
import { UiButton } from '../../../shared/components/ui-button/ui-button';
import { UiInput } from '../../../shared/components/ui-input/ui-input';
import { UiAlert } from '../../../shared/components/ui-alert/ui-alert';
import { DataTable } from '../../../shared/components/data-table/data-table';
import { DataTableCellDirective } from '../../../shared/components/data-table/data-table-cell.directive';
import { fetchAllPages } from '../../../shared/utils/fetch-all';
import { RoomEdit } from './room-edit/room-edit';
import { RoomBuildingMap } from './room-building-map/room-building-map';
import { TableColumn } from '../../../core/models/table-column';
import { Room } from '../../../core/models/catalog';

interface RoomForm {
  code: string;
  name: string;
  building: string;
}

@Component({
  selector: 'app-rooms-page',
  imports: [
    FormsModule,
    PageHeader,
    UiButton,
    UiInput,
    UiAlert,
    DialogModule,
    RoomEdit,
    RoomBuildingMap,
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
  readonly buildingRooms = signal<Room[]>([]);
  readonly selectedRoom = signal<Room | null>(null);
  readonly editingRoom = signal<Room | null>(null);
  readonly buildingMapLoading = signal(false);
  readonly buildingMapError = signal<string | null>(null);
  readonly total = signal(0);
  readonly loading = signal(false);
  readonly error = signal<string | null>(null);
  readonly saving = signal(false);

  readonly form = signal<RoomForm>({ code: '', name: '', building: '' });

  dialogVisible = false;

  constructor() {
    effect(() => {
      this.q();
      this.page();
      this.pageSize();
      void this.load();
    });
    void this.loadBuildingRooms();
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
    void this.loadBuildingRooms();
  }

  selectRoom(room: Room | null): void {
    this.selectedRoom.set(room);
  }

  openRoomEditor(room: Room): void {
    this.editingRoom.set(room);
  }

  closeRoomEditor(visible: boolean): void {
    if (!visible) this.editingRoom.set(null);
  }

  openCreate(): void {
    this.form.set({ code: '', name: '', building: '' });
    this.dialogVisible = true;
  }

  async save(): Promise<void> {
    const f = this.form();
    if (f.code.trim().length < 1) {
      this.toast.add({ severity: 'warn', summary: 'Falta el código', life: 2500 });
      return;
    }
    this.saving.set(true);
    try {
      await this.api
        .createRoom({ code: f.code.trim(), name: f.name, building: f.building })
        .toPromise();
      this.toast.add({ severity: 'success', summary: 'Aula creada', life: 2500 });
      this.dialogVisible = false;
      this.reload();
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

  private async loadBuildingRooms(): Promise<void> {
    this.buildingMapLoading.set(true);
    this.buildingMapError.set(null);
    try {
      const rooms = await fetchAllPages((params) => this.api.rooms(params));
      this.buildingRooms.set(rooms);
      const selected = this.selectedRoom();
      if (selected) {
        this.selectedRoom.set(rooms.find((room) => room.id === selected.id) ?? null);
      }
    } catch (err) {
      this.buildingMapError.set(extractDetail(err));
    } finally {
      this.buildingMapLoading.set(false);
    }
  }
}
