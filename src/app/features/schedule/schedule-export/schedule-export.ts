import {
  ChangeDetectionStrategy,
  Component,
  CUSTOM_ELEMENTS_SCHEMA,
  computed,
  effect,
  inject,
  input,
  model,
  signal,
  untracked,
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MessageService } from 'primeng/api';
import { DialogModule } from 'primeng/dialog';
import { SelectModule } from 'primeng/select';

import { ReportsApi } from '../../../core/services/reports-api';
import type { ScheduleExportFormat } from '../../../core/services/reports-api';
import { UiButton } from '../../../shared/components/ui-button/ui-button';
import { extractDetail } from '../../../shared/utils/api-error';
import { CYCLES, toRoman } from '../../../shared/utils/cycles';
import { saveBlob } from '../../../shared/utils/download';

interface FormatOption {
  readonly value: ScheduleExportFormat;
  readonly label: string;
  readonly hint: string;
  readonly icon: string;
}

export interface ScheduleExportFilters {
  readonly courseId: number;
  readonly teacherId: number;
  readonly roomId: number;
}

const FORMATS: FormatOption[] = [
  {
    value: 'pdf',
    label: 'PDF',
    hint: 'Para imprimir o compartir',
    icon: 'material-symbols:picture-as-pdf-outline',
  },
  {
    value: 'xlsx',
    label: 'Excel',
    hint: 'Una hoja por ciclo y una lista',
    icon: 'material-symbols:table-chart-outline',
  },
  {
    value: 'png',
    label: 'Imagen PNG',
    hint: 'Para chats y redes',
    icon: 'material-symbols:image-outline',
  },
];

@Component({
  selector: 'app-schedule-export',
  imports: [FormsModule, DialogModule, SelectModule, UiButton],
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  templateUrl: './schedule-export.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ScheduleExport {
  private readonly api = inject(ReportsApi);
  private readonly toast = inject(MessageService);

  readonly visible = model(false);
  readonly semesters = input.required<string[]>();
  readonly semester = input<string | null>(null);
  readonly cycle = input(0);
  readonly filters = input<ScheduleExportFilters>({ courseId: 0, teacherId: 0, roomId: 0 });

  readonly formats = FORMATS;
  readonly format = signal<ScheduleExportFormat>('pdf');
  readonly chosenSemester = signal<string | null>(null);
  readonly chosenCycle = signal(0);
  readonly showTeacher = signal(true);
  readonly showRoom = signal(true);
  readonly useFilters = signal(true);
  readonly busy = signal(false);

  readonly cycleOptions = [
    { label: 'Todos los ciclos', value: 0 },
    ...CYCLES.map((cycle) => ({ label: `Ciclo ${toRoman(cycle)}`, value: cycle })),
  ];

  readonly hasFilters = computed(() => {
    const filters = this.filters();
    return filters.courseId !== 0 || filters.teacherId !== 0 || filters.roomId !== 0;
  });
  readonly note = computed(() => {
    if (this.format() === 'png' && this.chosenCycle() === 0) {
      return 'Se descargará un ZIP con una imagen por ciclo.';
    }
    if (this.format() === 'xlsx') return 'El Excel incluye una hoja «Lista» con todas las clases.';
    return null;
  });

  constructor() {
    effect(() => {
      if (!this.visible()) return;
      untracked(() => {
        this.chosenSemester.set(this.semester());
        this.chosenCycle.set(this.cycle());
        this.useFilters.set(this.hasFilters());
      });
    });
  }

  async export(): Promise<void> {
    const filters = this.useFilters() ? this.filters() : null;
    this.busy.set(true);
    try {
      const file = await new Promise<{ blob: Blob; filename: string }>((resolve, reject) => {
        this.api
          .schedule({
            format: this.format(),
            semester: this.chosenSemester(),
            cycle: this.chosenCycle() || null,
            course_id: filters?.courseId || null,
            teacher_id: filters?.teacherId || null,
            room_id: filters?.roomId || null,
            show_teacher: this.showTeacher(),
            show_room: this.showRoom(),
          })
          .subscribe({ next: resolve, error: reject });
      });
      saveBlob(file.blob, file.filename);
      this.toast.add({
        severity: 'success',
        summary: 'Horario exportado',
        detail: file.filename,
        life: 3500,
      });
      this.visible.set(false);
    } catch (err) {
      this.toast.add({
        severity: 'error',
        summary: 'No se pudo exportar el horario',
        detail: extractDetail(await this.readBlobError(err)),
        life: 5000,
      });
    } finally {
      this.busy.set(false);
    }
  }

  private async readBlobError(err: unknown): Promise<unknown> {
    const body = (err as { error?: unknown }).error;
    if (!(body instanceof Blob)) return err;
    try {
      return { error: JSON.parse(await body.text()) };
    } catch {
      return err;
    }
  }
}
