import {
  ChangeDetectionStrategy,
  Component,
  CUSTOM_ELEMENTS_SCHEMA,
  computed,
  effect,
  inject,
  signal,
  viewChild,
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MessageService } from 'primeng/api';
import { DialogModule } from 'primeng/dialog';
import { SelectModule } from 'primeng/select';

import { QueryParams } from '../../../shared/utils/query-params';
import { extractDetail } from '../../../shared/utils/api-error';
import { CalendarApi } from '../../../core/services/calendar-api';
import { AuthService } from '../../../core/services/auth/auth';
import { PageHeader } from '../../../shared/components/page-header/page-header';
import { UiButton } from '../../../shared/components/ui-button/ui-button';
import { UiInput } from '../../../shared/components/ui-input/ui-input';
import { UiAlert } from '../../../shared/components/ui-alert/ui-alert';
import { ModalDelete } from '../../../shared/components/modal-delete/modal-delete';
import { DataTable } from '../../../shared/components/data-table/data-table';
import { DataTableCellDirective } from '../../../shared/components/data-table/data-table-cell.directive';
import { TableColumn } from '../../../core/models/table-column';
import { Holiday } from '../../../core/models/catalog';

@Component({
  selector: 'app-holidays',
  imports: [
    FormsModule, PageHeader, UiButton, UiInput, UiAlert, ModalDelete, DataTable,
    DataTableCellDirective, DialogModule, SelectModule,
  ],
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  templateUrl: './holidays.page.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class HolidaysPage {
  protected readonly auth = inject(AuthService);
  private readonly api = inject(CalendarApi);
  private readonly qp = inject(QueryParams);
  private readonly toast = inject(MessageService);
  private readonly deleteModal = viewChild(ModalDelete);

  readonly columns = computed<TableColumn[]>(() => [
    { id: 'index', header: 'N°', width: '60px', align: 'center' },
    { id: 'fecha', header: 'Fecha' },
    { id: 'dia', header: 'Día', hiddenOnMobile: true },
    { id: 'description', header: 'Motivo' },
    ...(this.auth.isAdmin()
      ? [{ id: 'actions', header: 'Acciones', align: 'right' as const, width: '90px' }]
      : []),
  ]);

  readonly currentYear = new Date().getFullYear();
  readonly yearOptions: Array<{ label: string; value: number }> = [
    { label: String(this.currentYear), value: this.currentYear },
    { label: String(this.currentYear + 1), value: this.currentYear + 1 },
    { label: String(this.currentYear - 1), value: this.currentYear - 1 },
  ];

  readonly yearUrl = this.qp.filter('year');
  readonly year = signal<number>(this.currentYear);

  readonly holidays = signal<Holiday[]>([]);
  readonly loading = signal(false);
  readonly error = signal<string | null>(null);
  readonly saving = signal(false);
  readonly deleting = signal(false);

  readonly form = signal({ holiday_date: '', description: '' });
  createVisible = false;

  readonly range = signal({ desde: '', hasta: '', description: '', omitir_fines_de_semana: true });
  rangeVisible = false;

  readonly nationalYear = signal(this.currentYear);

  readonly deleteTarget = signal<Holiday | null>(null);
  deleteVisible = false;

  constructor() {
    const urlYear = this.yearUrl();
    if (urlYear) this.year.set(Number(urlYear));
    effect(() => {
      this.year();
      void this.load();
    });
  }

  patch(p: Partial<{ holiday_date: string; description: string }>): void {
    this.form.update((f) => ({ ...f, ...p }));
  }

  patchRange(
    p: Partial<{ desde: string; hasta: string; description: string; omitir_fines_de_semana: boolean }>,
  ): void {
    this.range.update((r) => ({ ...r, ...p }));
  }

  onYear(value: number | null): void {
    this.year.set(value ?? this.currentYear);
    void this.qp.update({ year: value ?? null });
  }

  reload(): void {
    void this.load();
  }

  openCreate(): void {
    this.form.set({ holiday_date: '', description: '' });
    this.createVisible = true;
  }

  openRange(): void {
    this.range.set({ desde: '', hasta: '', description: '', omitir_fines_de_semana: true });
    this.rangeVisible = true;
  }

  async save(): Promise<void> {
    const f = this.form();
    if (!f.holiday_date || f.description.trim().length < 3) {
      this.toast.add({
        severity: 'warn',
        summary: 'Revisa el formulario',
        detail: 'Indica la fecha y un motivo de al menos 3 caracteres',
        life: 3500,
      });
      return;
    }
    this.saving.set(true);
    try {
      const res = await this.api
        .createHoliday({ holiday_date: f.holiday_date, description: f.description.trim() })
        .toPromise();
      this.toast.add({
        severity: 'success',
        summary: 'Feriado registrado',
        detail: res?.sesiones_canceladas
          ? `Se cancelaron ${res.sesiones_canceladas} sesión(es) de ese día`
          : 'No había sesiones abiertas o cerradas de ese día',
        life: 4500,
      });
      this.createVisible = false;
      void this.load();
    } catch (err) {
      this.toast.add({
        severity: 'error',
        summary: 'No se pudo registrar el feriado',
        detail: extractDetail(err),
        life: 5000,
      });
    } finally {
      this.saving.set(false);
    }
  }

  async saveRange(): Promise<void> {
    const r = this.range();
    if (!r.desde || !r.hasta || r.description.trim().length < 3) {
      this.toast.add({
        severity: 'warn',
        summary: 'Revisa el formulario',
        detail: 'Indica el rango de fechas y un motivo de al menos 3 caracteres',
        life: 3500,
      });
      return;
    }
    if (r.hasta < r.desde) {
      this.toast.add({ severity: 'warn', summary: 'La fecha final no puede ser anterior a la inicial', life: 4000 });
      return;
    }
    this.saving.set(true);
    try {
      const res = await this.api
        .createHolidayRange({
          desde: r.desde,
          hasta: r.hasta,
          description: r.description.trim(),
          omitir_fines_de_semana: r.omitir_fines_de_semana,
        })
        .toPromise();
      this.toast.add({
        severity: 'success',
        summary: 'Paro registrado',
        detail: `${res?.creados ?? 0} fecha(s) creada(s), ${res?.omitidos ?? 0} omitida(s) · ${res?.sesiones_canceladas ?? 0} sesión(es) cancelada(s)`,
        life: 6000,
      });
      this.rangeVisible = false;
      void this.load();
    } catch (err) {
      this.toast.add({
        severity: 'error',
        summary: 'No se pudo registrar el rango',
        detail: extractDetail(err),
        life: 5000,
      });
    } finally {
      this.saving.set(false);
    }
  }

  async loadNational(): Promise<void> {
    const year = this.nationalYear();
    this.saving.set(true);
    try {
      const res = await this.api.createNationalHolidays(year).toPromise();
      this.toast.add({
        severity: 'success',
        summary: `Feriados nacionales ${year}`,
        detail: `${res?.creados ?? 0} agregado(s) · ${res?.omitidos ?? 0} ya existían. Contrasta la lista con el calendario oficial vigente.`,
        life: 6000,
      });
      this.year.set(year);
      void this.qp.update({ year });
      void this.load();
    } catch (err) {
      this.toast.add({
        severity: 'error',
        summary: 'No se pudieron cargar los feriados nacionales',
        detail: extractDetail(err),
        life: 5000,
      });
    } finally {
      this.saving.set(false);
    }
  }

  askDelete(holiday: Holiday): void {
    this.deleteTarget.set(holiday);
    this.deleteVisible = true;
  }

  deleteLabel(): string | null {
    const h = this.deleteTarget();
    return h ? `${this.formatDate(h.holiday_date)} - ${h.description}` : null;
  }

  cancelDelete(): void {
    this.deleteTarget.set(null);
    this.deleteVisible = false;
  }

  async confirmDelete(): Promise<void> {
    const target = this.deleteTarget();
    if (!target) return;
    this.deleting.set(true);
    try {
      await this.api.deleteHoliday(target.id).toPromise();
      this.toast.add({
        severity: 'success',
        summary: 'Feriado eliminado',
        detail: 'Las sesiones que ya se cancelaron NO se reabren: vuelve a crearlas desde la programación.',
        life: 5000,
      });
      void this.load();
    } catch (err) {
      this.toast.add({
        severity: 'error',
        summary: 'No se pudo eliminar',
        detail: extractDetail(err),
        life: 4500,
      });
    } finally {
      this.deleteModal()?.done();
      this.deleting.set(false);
      this.deleteTarget.set(null);
      this.deleteVisible = false;
    }
  }

  formatDate(iso: string): string {
    if (!iso) return '-';
    return new Date(`${iso}T12:00:00`).toLocaleDateString('es-PE', {
      weekday: 'long',
      day: '2-digit',
      month: 'long',
      year: 'numeric',
    });
  }

  weekday(iso: string): string {
    if (!iso) return '-';
    const label = new Date(`${iso}T12:00:00`).toLocaleDateString('es-PE', { weekday: 'long' });
    return label.charAt(0).toUpperCase() + label.slice(1);
  }

  monthShort(iso: string): string {
    if (!iso) return '-';
    return new Date(`${iso}T12:00:00`)
      .toLocaleDateString('es-PE', { month: 'short' })
      .replace('.', '')
      .slice(0, 3);
  }

  countWeekend(): number {
    return this.holidays().filter((h) => this.isWeekend(h.holiday_date)).length;
  }

  isWeekend(iso: string): boolean {
    const day = new Date(`${iso}T12:00:00`).getDay();
    return day === 0 || day === 6;
  }

  private async load(): Promise<void> {
    this.loading.set(true);
    this.error.set(null);
    try {
      const list = await this.api.holidays(this.year()).toPromise();
      this.holidays.set(list ?? []);
    } catch (err) {
      this.error.set(extractDetail(err));
    } finally {
      this.loading.set(false);
    }
  }
}
