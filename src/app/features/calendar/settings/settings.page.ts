import { ChangeDetectionStrategy, Component, CUSTOM_ELEMENTS_SCHEMA, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MessageService } from 'primeng/api';
import { SelectModule } from 'primeng/select';

import { extractDetail } from '../../../shared/utils/api-error';
import { CalendarApi } from '../../../core/services/calendar-api';
import { UiButton } from '../../../shared/components/ui-button/ui-button';
import { UiInput } from '../../../shared/components/ui-input/ui-input';
import { UiAlert } from '../../../shared/components/ui-alert/ui-alert';
import { PageHeader } from '../../../shared/components/page-header/page-header';
import { Settings } from '../../../core/models/catalog';

interface Option<T> {
  label: string;
  value: T;
}

interface SettingsForm {
  semester_label: string;
  semester_start: string;
  semester_end: string;
  block_minutes: number;
  late_tolerance_minutes: number;
  early_open_minutes: number;
  rectify_days: number;
  dpi_min_sessions: number;
  face_match_threshold: number;
  dpi_alert_percent: number;
  dpi_limit_percent: number;
  attendance_hour_start: string;
  attendance_hour_end: string;
}

const EMPTY: SettingsForm = {
  semester_label: '',
  semester_start: '',
  semester_end: '',
  block_minutes: 60,
  late_tolerance_minutes: 10,
  early_open_minutes: 15,
  rectify_days: 7,
  dpi_min_sessions: 3,
  face_match_threshold: 0.55,
  dpi_alert_percent: 20,
  dpi_limit_percent: 30,
  attendance_hour_start: '06:00',
  attendance_hour_end: '22:00',
};

@Component({
  selector: 'app-settings',
  imports: [FormsModule, PageHeader, UiButton, UiInput, UiAlert, SelectModule],
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  templateUrl: './settings.page.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class SettingsPage {
  private readonly api = inject(CalendarApi);
  private readonly toast = inject(MessageService);

  readonly loading = signal(true);
  readonly saving = signal(false);
  readonly error = signal<string | null>(null);
  readonly updatedAt = signal<string | null>(null);

  readonly form = signal<SettingsForm>({ ...EMPTY });
  private readonly original = signal<SettingsForm>({ ...EMPTY });

  readonly blockMinutesOptions: Option<number>[] = [
    { label: '45 minutos', value: 45 },
    { label: '50 minutos', value: 50 },
    { label: '60 minutos (1 h)', value: 60 },
    { label: '90 minutos', value: 90 },
    { label: '120 minutos (2 h)', value: 120 },
  ];
  readonly toleranceOptions: Option<number>[] = [0, 5, 10, 15, 20, 30].map((v) => ({
    label: v === 0 ? 'Sin tolerancia' : `${v} minutos`,
    value: v,
  }));
  readonly earlyOpenOptions: Option<number>[] = [0, 5, 10, 15, 30, 45, 60].map((v) => ({
    label: v === 0 ? 'Solo durante el bloque' : `${v} minutos antes`,
    value: v,
  }));
  readonly rectifyOptions: Option<number>[] = [0, 1, 3, 7, 15, 30].map((v) => ({
    label: v === 0 ? 'Solo el mismo día' : `${v} día(s)`,
    value: v,
  }));
  readonly minSessionsOptions: Option<number>[] = [0, 1, 2, 3, 5, 8, 10].map((v) => ({
    label: v === 0 ? 'Desde la primera sesión' : `${v} sesión(es)`,
    value: v,
  }));

  readonly problems = computed<string[]>(() => {
    const f = this.form();
    const out: string[] = [];
    if (f.semester_label.trim().length < 3) out.push('El semestre necesita al menos 3 caracteres (ej. 2026-II)');
    if (f.semester_start && f.semester_end && f.semester_start >= f.semester_end)
      out.push('El inicio del semestre debe ser anterior a su fin');
    if (f.attendance_hour_start >= f.attendance_hour_end)
      out.push('La hora de inicio de la ventana de marca debe ser menor que la hora de fin');
    if (f.dpi_alert_percent >= f.dpi_limit_percent)
      out.push('El porcentaje de alerta DPI debe ser menor que el porcentaje de límite (30 %)');
    if (f.face_match_threshold <= 0 || f.face_match_threshold > 1)
      out.push('El umbral facial debe estar entre 0 y 1 (recomendado 0.55)');
    if (f.block_minutes <= 0) out.push('La duración de bloque debe ser mayor que 0');
    return out;
  });

  readonly changed = computed(() => {
    const a = this.form();
    const b = this.original();
    const keys = Object.keys(a) as Array<keyof SettingsForm>;
    return keys.filter((k) => a[k] !== b[k]);
  });

  readonly canSave = computed(() => this.problems().length === 0 && this.changed().length > 0);

  constructor() {
    void this.load();
  }

  patch(p: Partial<SettingsForm>): void {
    this.form.update((f) => ({ ...f, ...p }));
  }

  reload(): void {
    void this.load();
  }

  restore(): void {
    this.form.set({ ...this.original() });
    this.toast.add({ severity: 'info', summary: 'Cambios descartados', life: 2500 });
  }

  async save(): Promise<void> {
    if (this.problems().length > 0) {
      this.toast.add({
        severity: 'warn',
        summary: 'Revisa los valores',
        detail: this.problems()[0],
        life: 4500,
      });
      return;
    }
    if (this.changed().length === 0) {
      this.toast.add({ severity: 'info', summary: 'No hay cambios por guardar', life: 2500 });
      return;
    }
    const patch: Record<string, string | number> = {};
    for (const key of this.changed()) {
      const value = this.form()[key];
      patch[key] = typeof value === 'string' ? value.trim() : value;
    }
    this.saving.set(true);
    try {
      const res = await this.api.updateSettings(patch).toPromise();
      if (res) this.apply(res);
      this.toast.add({
        severity: 'success',
        summary: 'Parámetros actualizados',
        detail: 'Aplican a las sesiones siguientes; las ya registradas no cambian (RF-34)',
        life: 5000,
      });
    } catch (err) {
      this.toast.add({
        severity: 'error',
        summary: 'No se pudieron guardar los parámetros',
        detail: extractDetail(err),
        life: 5500,
      });
    } finally {
      this.saving.set(false);
    }
  }

  private apply(s: Settings): void {
    const next: SettingsForm = {
      semester_label: s.semester_label,
      semester_start: s.semester_start ?? '',
      semester_end: s.semester_end ?? '',
      block_minutes: s.block_minutes,
      late_tolerance_minutes: s.late_tolerance_minutes,
      early_open_minutes: s.early_open_minutes,
      rectify_days: s.rectify_days,
      dpi_min_sessions: s.dpi_min_sessions,
      face_match_threshold: s.face_match_threshold,
      dpi_alert_percent: s.dpi_alert_percent,
      dpi_limit_percent: s.dpi_limit_percent,
      attendance_hour_start: s.attendance_hour_start.slice(0, 5),
      attendance_hour_end: s.attendance_hour_end.slice(0, 5),
    };
    this.form.set({ ...next });
    this.original.set({ ...next });
    this.updatedAt.set(s.updated_at);
  }

  private async load(): Promise<void> {
    this.loading.set(true);
    this.error.set(null);
    try {
      const s = await this.api.settings().toPromise();
      if (s) this.apply(s);
    } catch (err) {
      this.error.set(extractDetail(err));
    } finally {
      this.loading.set(false);
    }
  }
}
