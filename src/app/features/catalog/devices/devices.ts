import {
  ChangeDetectionStrategy,
  Component,
  CUSTOM_ELEMENTS_SCHEMA,
  DestroyRef,
  computed,
  effect,
  inject,
  signal,
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { MessageService } from 'primeng/api';
import { DialogModule } from 'primeng/dialog';
import { InputTextModule } from 'primeng/inputtext';
import { SelectModule } from 'primeng/select';
import { ToggleSwitchModule } from 'primeng/toggleswitch';
import { interval } from 'rxjs';

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
import { Device, DeviceType, Room } from '../../../core/models/catalog';
import { extractDetail } from '../rooms/rooms';

const REFRESH_MONITOREO_MS = 30_000; // RF-35: panel de monitoreo cada 30 s

interface DeviceForm {
  id: number | null;
  room_id: number | null;
  device_type: DeviceType;
  device_key: string;
  name: string;
  rtsp_url: string;
  is_active: boolean;
}

@Component({
  selector: 'app-devices-page',
  imports: [
    FormsModule, PageHeader, UiButton, UiInput, UiAlert, DataTable, DataTableCellDirective,
    DialogModule, InputTextModule, SelectModule, ToggleSwitchModule,
  ],
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  templateUrl: './devices.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class DevicesPage {
  protected readonly auth = inject(AuthService);
  private readonly api = inject(CatalogApi);
  private readonly qp = inject(QueryParams);
  private readonly toast = inject(MessageService);
  private readonly destroyRef = inject(DestroyRef);

  readonly tab = this.qp.filter('tab');
  readonly roomId = this.qp.filter('room_id');
  readonly tipo = this.qp.filter('device_type');
  readonly page = this.qp.number('page', 1);
  readonly pageSize = this.qp.number('page_size', 10);

  readonly devices = signal<Device[]>([]);
  readonly total = signal(0);
  readonly statusList = signal<Device[]>([]);
  readonly lastRefresh = signal('—');
  readonly loading = signal(false);
  readonly error = signal<string | null>(null);
  readonly saving = signal(false);
  readonly aulas = signal<{ label: string; value: number }[]>([]);

  readonly tipos = [
    { label: 'Cámara (RTSP)', value: 'camara' as DeviceType },
    { label: 'Nodo ESP32', value: 'esp32' as DeviceType },
  ];

  readonly columns: TableColumn[] = [
    { id: 'index', header: 'N°', width: '60px', align: 'center' },
    { id: 'device', header: 'Dispositivo' },
    { id: 'room_code', header: 'Aula' },
    { id: 'rtsp_url', header: 'RTSP', hiddenOnMobile: true },
    { id: 'is_online', header: 'Estado', align: 'center' },
    { id: 'actions', header: '', align: 'center', width: '70px' },
  ];

  readonly form = signal<DeviceForm>({
    id: null, room_id: null, device_type: 'camara', device_key: '', name: '', rtsp_url: '', is_active: true,
  });

  dialogVisible = false;

  readonly onlineCount = computed(() => this.statusList().filter((d) => d.is_online).length);

  constructor() {
    effect(() => {
      this.roomId(); this.tipo(); this.page(); this.pageSize();
      if (this.tab() !== 'monitoreo') void this.load();
    });
    effect(() => {
      if (this.tab() === 'monitoreo') void this.loadStatus();
    });

    // RF-35: auto-refresh del monitoreo cada 30 s
    interval(REFRESH_MONITOREO_MS)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => {
        if (this.tab() === 'monitoreo') void this.loadStatus();
      });

    void this.loadRooms();
  }

  shortRtsp(url: string): string {
    try {
      const u = new URL(url.replace('rtsp://', 'http://'));
      return `rtsp://…@${u.host}${u.pathname}`;
    } catch {
      return url.slice(0, 28) + '…';
    }
  }

  shortTime(iso: string): string {
    return iso.length >= 16 ? iso.slice(11, 16) : iso;
  }

  isMonitoreo(): boolean {
    return this.tab() === 'monitoreo';
  }

  setTab(tab: 'catalogo' | 'monitoreo'): void {
    void this.qp.update({ tab: tab === 'monitoreo' ? 'monitoreo' : null });
  }

  onRoomFilter(value: number | string | null): void {
    void this.qp.update({ room_id: value ? String(value) : null, page: null });
  }

  onTypeFilter(value: DeviceType | null): void {
    void this.qp.update({ device_type: value ?? null, page: null });
  }

  onPage(p: number): void { void this.qp.update({ page: p }); }
  onPageSize(s: number): void { void this.qp.update({ page_size: s, page: null }); }
  reload(): void { void this.load(); }

  patch(p: Partial<DeviceForm>): void {
    this.form.update((f) => ({ ...f, ...p }));
  }

  openCreate(): void {
    this.form.set({ id: null, room_id: null, device_type: 'camara', device_key: '', name: '', rtsp_url: '', is_active: true });
    this.dialogVisible = true;
  }

  openEdit(d: Device): void {
    this.form.set({
      id: d.id, room_id: d.room_id, device_type: d.device_type, device_key: d.device_key,
      name: d.name ?? '', rtsp_url: d.rtsp_url ?? '', is_active: d.is_active,
    });
    this.dialogVisible = true;
  }

  async save(): Promise<void> {
    const f = this.form();
    this.saving.set(true);
    try {
      if (f.id === null) {
        if (!f.room_id || !f.device_key.trim()) {
          this.toast.add({ severity: 'warn', summary: 'Completa aula y device_key', life: 3000 });
          return;
        }
        if (f.device_type === 'camara' && !f.rtsp_url?.trim()) {
          this.toast.add({ severity: 'warn', summary: 'La cámara requiere su URL RTSP', life: 3000 });
          return;
        }
        await this.api.createDevice({
          room_id: f.room_id, device_type: f.device_type, device_key: f.device_key.trim().toLowerCase(),
          name: f.name || null, rtsp_url: f.rtsp_url || null,
        }).toPromise();
        this.toast.add({ severity: 'success', summary: 'Dispositivo registrado', life: 2500 });
      } else {
        await this.api.updateDevice(f.id, {
          name: f.name || null, rtsp_url: f.rtsp_url || null, is_active: f.is_active,
        }).toPromise();
        this.toast.add({ severity: 'success', summary: 'Dispositivo actualizado', life: 2500 });
      }
      this.dialogVisible = false;
      void this.load();
    } catch (err) {
      this.toast.add({ severity: 'error', summary: 'No se pudo guardar', detail: extractDetail(err), life: 4500 });
    } finally {
      this.saving.set(false);
    }
  }

  private async loadRooms(): Promise<void> {
    try {
      const res = await this.api.rooms({ page_size: 100 }).toPromise();
      this.aulas.set((res?.items ?? []).map((r: Room) => ({ label: r.code, value: r.id })));
    } catch {
      // el select queda vacío; no bloquea la pantalla
    }
  }

  private async load(): Promise<void> {
    this.loading.set(true);
    this.error.set(null);
    try {
      const res = await this.api.devices({
        page: this.page(), page_size: this.pageSize(),
        room_id: this.roomId() ? Number(this.roomId()) : undefined,
        device_type: (this.tipo() as DeviceType) ?? undefined,
      }).toPromise();
      this.devices.set(res?.items ?? []);
      this.total.set(res?.total ?? 0);
    } catch (err) {
      this.error.set(extractDetail(err));
    } finally {
      this.loading.set(false);
    }
  }

  private async loadStatus(): Promise<void> {
    try {
      const list = await this.api.deviceStatus().toPromise();
      this.statusList.set(list ?? []);
      this.lastRefresh.set(
        new Date().toLocaleTimeString('es-PE', { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
      );
    } catch (err) {
      this.toast.add({ severity: 'error', summary: 'Monitoreo', detail: extractDetail(err), life: 3500 });
    }
  }
}
