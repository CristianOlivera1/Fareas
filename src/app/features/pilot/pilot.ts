import { ChangeDetectionStrategy, Component, CUSTOM_ELEMENTS_SCHEMA, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { SelectModule } from 'primeng/select';

import { PilotApi, PilotRate, PilotStatus } from '../../core/services/pilot-api';
import { PageHeader } from '../../shared/components/page-header/page-header';
import { UiAlert } from '../../shared/components/ui-alert/ui-alert';
import { UiButton } from '../../shared/components/ui-button/ui-button';
import { extractDetail } from '../../shared/utils/api-error';
import { saveBlob } from '../../shared/utils/download';

const TARGET_PER_CONDITION = 3;

interface Option<T> {
  readonly label: string;
  readonly value: T;
}

@Component({
  selector: 'app-pilot-page',
  imports: [FormsModule, SelectModule, PageHeader, UiButton, UiAlert],
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  templateUrl: './pilot.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { class: 'block' },
})
export class PilotPage {
  private readonly api = inject(PilotApi);

  readonly targetPerCondition = TARGET_PER_CONDITION;
  readonly conditionOptions: Option<'normal' | 'adversa'>[] = [
    { label: 'Normal (luz habitual, sin accesorios)', value: 'normal' },
    { label: 'Adversa (luz lateral, lentes o distancia distinta)', value: 'adversa' },
  ];

  readonly status = signal<PilotStatus | null>(null);
  readonly loading = signal(true);
  readonly capturing = signal(false);
  readonly error = signal<string | null>(null);
  readonly message = signal<string | null>(null);

  readonly studentId = signal<number | null>(null);
  readonly unenrolled = signal(false);
  readonly condition = signal<'normal' | 'adversa'>('normal');
  readonly seconds = signal(10);
  readonly threshold = signal(0.55);
  readonly margin = signal(0.06);
  readonly confirm = signal(3);

  readonly studentOptions = computed<Option<number>[]>(() =>
    (this.status()?.students ?? []).map((student) => ({
      label: `${student.alias} · ${student.code ?? 'sin código'} · ${student.name}`,
      value: student.id,
    })),
  );
  readonly canCapture = computed(
    () => !this.capturing() && (this.unenrolled() || this.studentId() !== null) && this.status()?.camera_room !== null,
  );
  readonly pending = computed(() => {
    const students = this.status()?.students ?? [];
    return students.filter(
      (student) => student.normal < TARGET_PER_CONDITION || student.adversa < TARGET_PER_CONDITION,
    ).length;
  });

  constructor() {
    this.refresh();
  }

  refresh(): void {
    this.api
      .status({ threshold: this.threshold(), margin: this.margin(), confirm: this.confirm() })
      .subscribe({
        next: (status) => {
          this.status.set(status);
          this.loading.set(false);
        },
        error: (err) => {
          this.error.set(extractDetail(err));
          this.loading.set(false);
        },
      });
  }

  setNumber(field: 'threshold' | 'margin' | 'confirm' | 'seconds', value: string): void {
    const parsed = Number(value);
    if (!Number.isFinite(parsed)) return;
    this[field].set(parsed);
    if (field !== 'seconds') this.refresh();
  }

  toggleUnenrolled(checked: boolean): void {
    this.unenrolled.set(checked);
    if (checked) this.studentId.set(null);
  }

  capture(): void {
    if (!this.canCapture()) return;
    this.capturing.set(true);
    this.error.set(null);
    this.message.set(null);
    this.api
      .capture({
        student_id: this.unenrolled() ? null : this.studentId(),
        condition: this.condition(),
        seconds: this.seconds(),
      })
      .subscribe({
        next: (result) => {
          this.capturing.set(false);
          this.message.set(
            result.frames > 0
              ? `Captura guardada: ${result.frames} cuadros con rostro (${result.alias}, ${result.condition}).`
              : 'La captura terminó sin detectar ningún rostro. Repítela acercándote a la cámara.',
          );
          this.refresh();
        },
        error: (err) => {
          this.capturing.set(false);
          this.error.set(extractDetail(err));
        },
      });
  }

  download(): void {
    this.api.exportCsv().subscribe({
      next: (file) => saveBlob(file.blob, file.filename),
      error: (err) => this.error.set(extractDetail(err)),
    });
  }

  reset(): void {
    if (!confirm('Se borrarán todas las capturas del piloto. ¿Continuar?')) return;
    this.api.reset().subscribe({
      next: () => {
        this.message.set('Datos del piloto borrados.');
        this.refresh();
      },
      error: (err) => this.error.set(extractDetail(err)),
    });
  }

  percent(value: number | null): string {
    return value === null ? '—' : `${(value * 100).toFixed(1)} %`;
  }

  interval(rate: PilotRate): string {
    if (rate.total === 0 || rate.low === null || rate.high === null) return 'sin datos';
    return `IC 95 %: ${this.percent(rate.low)} a ${this.percent(rate.high)} · n = ${rate.total}`;
  }
}
