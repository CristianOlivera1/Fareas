import {
  ChangeDetectionStrategy,
  Component,
  CUSTOM_ELEMENTS_SCHEMA,
  computed,
  inject,
  model,
  output,
  signal,
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MessageService } from 'primeng/api';
import { DialogModule } from 'primeng/dialog';
import { SelectModule } from 'primeng/select';
import { firstValueFrom } from 'rxjs';

import { CurriculumEditableRow, CurriculumPreview, CurriculumResult } from '../../../core/models/imports';
import { CoursesApi } from '../../../core/services/courses-api';
import { extractDetail } from '../../../shared/utils/api-error';
import { CYCLES, toRoman } from '../../../shared/utils/cycles';
import { FileDrop } from '../../../shared/components/file-drop/file-drop';
import { UiAlert } from '../../../shared/components/ui-alert/ui-alert';
import { UiButton } from '../../../shared/components/ui-button/ui-button';
import { ScanLoader } from '../../../shared/components/scan-loader/scan-loader';

type CycleFilter = 'all' | number;

interface Option<T> {
  readonly label: string;
  readonly value: T;
}

const STEPS = [
  { number: 1, label: 'Archivo' },
  { number: 2, label: 'Revisar malla' },
  { number: 3, label: 'Resultado' },
];

const CODE_PATTERN = /^[A-Z0-9]{3,20}$/;

const CYCLE_OPTIONS: Option<number>[] = CYCLES.map((cycle) => ({
  label: `Ciclo ${toRoman(cycle)}`,
  value: cycle,
}));

const DEFAULT_CYCLE_OPTIONS: Option<number | null>[] = [
  { label: 'Detectar automáticamente', value: null },
  ...CYCLE_OPTIONS,
];

@Component({
  selector: 'app-courses-import-dialog',
  imports: [FormsModule, DialogModule, SelectModule, UiButton, UiAlert, FileDrop, ScanLoader],
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  templateUrl: './courses-import.dialog.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class CoursesImportDialog {
  private readonly api = inject(CoursesApi);
  private readonly toast = inject(MessageService);

  readonly visible = model(false);
  readonly imported = output<void>();

  readonly steps = STEPS;
  readonly cycleOptions = CYCLE_OPTIONS;
  readonly defaultCycleOptions = DEFAULT_CYCLE_OPTIONS;

  readonly step = signal(1);
  readonly file = signal<File | null>(null);
  readonly defaultCycle = signal<number | null>(null);
  readonly preview = signal<CurriculumPreview | null>(null);
  readonly rows = signal<CurriculumEditableRow[]>([]);
  readonly result = signal<CurriculumResult | null>(null);
  readonly filter = signal<CycleFilter>('all');
  readonly loading = signal(false);
  readonly confirming = signal(false);
  readonly error = signal<string | null>(null);

  private nextKey = 0;

  readonly toCreate = computed(() => this.rows().filter((row) => !row.ya_existe));
  readonly invalidCount = computed(
    () => this.toCreate().filter((row) => this.issues(row).length > 0).length,
  );
  readonly reviewCount = computed(
    () => this.toCreate().filter((row) => this.issues(row).length === 0 && !row.confiable).length,
  );
  readonly existingCount = computed(() => this.rows().filter((row) => row.ya_existe).length);
  readonly canRead = computed(() => this.file() !== null && !this.loading());
  readonly canConfirm = computed(
    () => this.toCreate().length > 0 && this.invalidCount() === 0 && !this.confirming(),
  );

  readonly tabs = computed(() => {
    const counts = new Map<number, number>();
    for (const row of this.rows()) {
      if (row.cycle !== null) counts.set(row.cycle, (counts.get(row.cycle) ?? 0) + 1);
    }
    const withoutCycle = this.rows().filter((row) => row.cycle === null).length;
    const tabs: Array<{ value: CycleFilter; label: string; count: number }> = [
      { value: 'all', label: 'Todos', count: this.rows().length },
      ...[...counts.keys()]
        .sort((a, b) => a - b)
        .map((cycle) => ({ value: cycle, label: toRoman(cycle), count: counts.get(cycle) ?? 0 })),
    ];
    if (withoutCycle > 0) tabs.push({ value: 0, label: 'Sin ciclo', count: withoutCycle });
    return tabs;
  });

  readonly visibleRows = computed(() => {
    const filter = this.filter();
    if (filter === 'all') return this.rows();
    return this.rows().filter((row) => (filter === 0 ? row.cycle === null : row.cycle === filter));
  });

  readonly typeLabel = computed(() => {
    const type = this.preview()?.tipo;
    if (type === 'pdf_texto') return 'PDF con texto';
    if (type === 'pdf_ocr') return 'PDF escaneado';
    if (type === 'imagen') return 'Imagen';
    return 'Documento';
  });

  onShow(): void {
    this.reset();
  }

  onHide(): void {
    if (this.result()?.creados) this.imported.emit();
  }

  close(): void {
    this.visible.set(false);
  }

  onFile(file: File | null): void {
    this.file.set(file);
    this.preview.set(null);
    this.rows.set([]);
    this.error.set(null);
  }

  onFileError(message: string): void {
    this.toast.add({ severity: 'error', summary: 'Archivo no válido', detail: message, life: 4500 });
  }

  async readCurriculum(): Promise<void> {
    const file = this.file();
    if (!file) return;
    this.loading.set(true);
    this.error.set(null);
    try {
      const preview = await firstValueFrom(this.api.importCurriculum(file, this.defaultCycle()));
      this.preview.set(preview);
      this.nextKey = 0;
      this.rows.set(
        preview.cursos.map((course) => ({
          key: this.newKey(),
          code: course.code,
          name: course.name,
          cycle: course.cycle,
          confiable: course.confiable,
          nota: course.nota,
          linea: course.linea,
          ya_existe: course.ya_existe,
          existente: course.existente,
        })),
      );
      this.filter.set('all');
      this.step.set(2);
      this.toast.add({
        severity: preview.por_revisar > 0 ? 'warn' : 'success',
        summary: `${preview.total} curso(s) detectado(s)`,
        detail:
          preview.por_revisar > 0
            ? `${preview.por_revisar} requieren revisión antes de confirmar.`
            : 'Revisa la malla por ciclo y confirma para registrarla.',
        life: 4500,
      });
    } catch (err) {
      this.error.set(extractDetail(err));
    } finally {
      this.loading.set(false);
    }
  }

  setFilter(filter: CycleFilter): void {
    this.filter.set(filter);
  }

  updateRow(key: string, patch: Partial<CurriculumEditableRow>): void {
    this.rows.update((rows) =>
      rows.map((row) =>
        row.key === key ? { ...row, ...patch, confiable: true, nota: null, ya_existe: false, existente: null } : row,
      ),
    );
  }

  onCode(key: string, event: Event): void {
    const value = (event.target as HTMLInputElement).value.toUpperCase().replace(/[^A-Z0-9]/g, '');
    this.updateRow(key, { code: value });
  }

  onName(key: string, event: Event): void {
    this.updateRow(key, { name: (event.target as HTMLInputElement).value });
  }

  onCycle(key: string, cycle: number | null): void {
    this.updateRow(key, { cycle });
  }

  addRow(): void {
    const filter = this.filter();
    this.rows.update((rows) => [
      ...rows,
      {
        key: this.newKey(),
        code: '',
        name: '',
        cycle: typeof filter === 'number' && filter > 0 ? filter : null,
        confiable: false,
        nota: 'Fila añadida a mano',
        linea: '',
        ya_existe: false,
        existente: null,
      },
    ]);
  }

  removeRow(key: string): void {
    this.rows.update((rows) => rows.filter((row) => row.key !== key));
  }

  removeInvalid(): void {
    this.rows.update((rows) => rows.filter((row) => row.ya_existe || this.issues(row).length === 0));
  }

  removeExisting(): void {
    this.rows.update((rows) => rows.filter((row) => !row.ya_existe));
  }

  issues(row: CurriculumEditableRow): string[] {
    if (row.ya_existe) return [];
    const issues: string[] = [];
    if (!CODE_PATTERN.test(row.code.trim())) issues.push('Código de 3 a 20 letras o números');
    if (row.name.trim().length < 3) issues.push('Nombre del curso');
    if (row.cycle === null) issues.push('Ciclo');
    const code = row.code.trim();
    if (code && this.toCreate().filter((other) => other.code.trim() === code).length > 1) {
      issues.push('Código repetido en la lista');
    }
    return issues;
  }

  issuesText(row: CurriculumEditableRow): string {
    return this.issues(row).join(' · ');
  }

  statusOf(row: CurriculumEditableRow): 'exists' | 'fix' | 'review' | 'ready' {
    if (row.ya_existe) return 'exists';
    if (this.issues(row).length > 0) return 'fix';
    return row.confiable ? 'ready' : 'review';
  }

  roman(cycle: number | null): string {
    return cycle === null ? '—' : toRoman(cycle);
  }

  async confirm(): Promise<void> {
    if (!this.canConfirm()) return;
    this.confirming.set(true);
    try {
      const result = await firstValueFrom(
        this.api.confirmCurriculum({
          cursos: this.toCreate().map((row) => ({
            code: row.code.trim().toUpperCase(),
            name: row.name.trim(),
            cycle: row.cycle as number,
          })),
        }),
      );
      this.result.set(result);
      this.step.set(3);
      this.toast.add({
        severity: 'success',
        summary: 'Malla registrada',
        detail: `${result.creados} curso(s) creados, ${result.omitidos} ya existían.`,
        life: 4500,
      });
    } catch (err) {
      this.toast.add({
        severity: 'error',
        summary: 'No se pudo registrar la malla',
        detail: extractDetail(err),
        life: 7000,
      });
    } finally {
      this.confirming.set(false);
    }
  }

  restart(): void {
    if (this.result()?.creados) this.imported.emit();
    this.reset();
  }

  private reset(): void {
    this.step.set(1);
    this.file.set(null);
    this.defaultCycle.set(null);
    this.preview.set(null);
    this.rows.set([]);
    this.result.set(null);
    this.filter.set('all');
    this.error.set(null);
    this.nextKey = 0;
  }

  private newKey(): string {
    this.nextKey += 1;
    return `course-${this.nextKey}`;
  }
}
