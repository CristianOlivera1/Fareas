import {
  ChangeDetectionStrategy,
  Component,
  CUSTOM_ELEMENTS_SCHEMA,
  computed,
  inject,
  signal,
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MessageService } from 'primeng/api';
import { DialogModule } from 'primeng/dialog';
import { firstValueFrom } from 'rxjs';

import { Settings } from '../../../core/models/catalog';
import { CalendarApi } from '../../../core/services/calendar-api';
import { extractDetail } from '../../../shared/utils/api-error';
import { PageHeader } from '../../../shared/components/page-header/page-header';
import { Tabs, TabOption } from '../../../shared/components/tabs/tabs';
import { UiButton } from '../../../shared/components/ui-button/ui-button';
import { EnrollmentsPage } from '../enrollments/enrollments';
import { CycleEnrollment } from './cycle-enrollment';

type Panel = 'cycle' | 'group';

const TABS: readonly TabOption[] = [
  { id: 'cycle', label: 'Por ciclo', icon: 'material-symbols:groups-outline' },
  { id: 'group', label: 'Por grupo', icon: 'material-symbols:person-add-outline' },
];

function todayIso(): string {
  const now = new Date();
  const month = String(now.getMonth() + 1).padStart(2, '0');
  const day = String(now.getDate()).padStart(2, '0');
  return `${now.getFullYear()}-${month}-${day}`;
}

function addDays(iso: string, days: number): string {
  const date = new Date(`${iso}T12:00:00`);
  date.setDate(date.getDate() + days);
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${date.getFullYear()}-${month}-${day}`;
}

@Component({
  selector: 'app-enrollment-center-page',
  imports: [FormsModule, DialogModule, PageHeader, Tabs, UiButton, CycleEnrollment, EnrollmentsPage],
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  templateUrl: './enrollment-center.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class EnrollmentCenterPage {
  private readonly calendar = inject(CalendarApi);
  private readonly toast = inject(MessageService);

  readonly tabs = TABS;
  readonly panel = signal<Panel>('cycle');
  readonly settings = signal<Settings | null>(null);
  readonly saving = signal(false);
  windowVisible = false;
  readonly start = signal('');
  readonly end = signal('');

  readonly period = computed(() => this.settings()?.semester_label ?? '');
  readonly windowOpen = computed(() => {
    const settings = this.settings();
    const start = settings?.enrollment_start;
    const end = settings?.enrollment_end;
    const today = todayIso();
    return !!start && !!end && start <= today && today <= end;
  });
  readonly windowLabel = computed(() => {
    const settings = this.settings();
    const start = settings?.enrollment_start;
    const end = settings?.enrollment_end;
    if (!start || !end) return 'Matrícula de estudiantes cerrada';
    if (this.windowOpen()) return `Matrícula de estudiantes abierta hasta el ${this.format(end)}`;
    return todayIso() < start
      ? `La matrícula de estudiantes abre el ${this.format(start)}`
      : `La matrícula de estudiantes cerró el ${this.format(end)}`;
  });
  readonly invalidWindow = computed(() => !!this.start() && !!this.end() && this.start() > this.end());

  constructor() {
    void this.load();
  }

  setPanel(id: string): void {
    this.panel.set(id as Panel);
  }

  openWindow(): void {
    const settings = this.settings();
    this.start.set(settings?.enrollment_start ?? todayIso());
    this.end.set(settings?.enrollment_end ?? addDays(todayIso(), 7));
    this.windowVisible = true;
  }

  quickRange(days: number): void {
    this.start.set(todayIso());
    this.end.set(addDays(todayIso(), days));
  }

  async saveWindow(): Promise<void> {
    if (!this.start() || !this.end() || this.invalidWindow()) return;
    await this.update({ enrollment_start: this.start(), enrollment_end: this.end() }, 'Ventana de matrícula guardada');
  }

  async closeWindow(): Promise<void> {
    await this.update({ enrollment_start: null, enrollment_end: null }, 'Matrícula de estudiantes cerrada');
  }

  private async update(
    body: { enrollment_start: string | null; enrollment_end: string | null },
    message: string,
  ): Promise<void> {
    this.saving.set(true);
    try {
      this.settings.set(await firstValueFrom(this.calendar.updateSettings(body)));
      this.windowVisible = false;
      this.toast.add({ severity: 'success', summary: message, life: 3500 });
    } catch (err) {
      this.toast.add({ severity: 'error', summary: 'No se pudo guardar', detail: extractDetail(err), life: 5000 });
    } finally {
      this.saving.set(false);
    }
  }

  private async load(): Promise<void> {
    try {
      this.settings.set(await firstValueFrom(this.calendar.settings()));
    } catch {
      this.settings.set(null);
    }
  }

  private format(iso: string): string {
    const [year, month, day] = iso.split('-');
    return `${day}/${month}/${year}`;
  }
}
