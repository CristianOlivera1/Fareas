import {
  ChangeDetectionStrategy,
  Component,
  CUSTOM_ELEMENTS_SCHEMA,
  computed,
  inject,
  signal,
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { MessageService } from 'primeng/api';
import { SelectModule } from 'primeng/select';

import { PageHeader } from '../../../shared/components/page-header/page-header';
import { UiAlert } from '../../../shared/components/ui-alert/ui-alert';
import { UiButton } from '../../../shared/components/ui-button/ui-button';
import { FileDrop } from '../../../shared/components/file-drop/file-drop';
import { CoursesApi } from '../../../core/services/courses-api';
import { CatalogApi } from '../../../core/services/catalog-api';
import { CalendarApi } from '../../../core/services/calendar-api';
import { extractDetail } from '../../../shared/utils/api-error';
import { CYCLES, toRoman } from '../../../shared/utils/cycles';
import type {
  ScheduleImportPreview,
  ScheduleImportResult,
  ScheduleImportRow,
} from '../../../core/models/imports';
import { LECTURE_WEEKDAYS } from '../../../shared/utils/weekdays';
import { formatTime } from '../../../shared/utils/schedule-hours';
import {
  groupScheduleImportRows,
  scheduleImportRowIssues,
} from '../../../shared/utils/schedule-import';
import type { ScheduleImportGroup } from '../../../shared/utils/schedule-import';

interface Option<T> {
  readonly label: string;
  readonly value: T;
}

const STEPS = [
  { number: 1, label: 'Archivo y contexto' },
  { number: 2, label: 'Revisar bloques' },
  { number: 3, label: 'Resultado' },
];

@Component({
  selector: 'app-schedule-import-page',
  imports: [FormsModule, PageHeader, UiButton, UiAlert, FileDrop, SelectModule],
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  templateUrl: './schedule-import.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ScheduleImportPage {
  private readonly api = inject(CoursesApi);
  private readonly catalog = inject(CatalogApi);
  private readonly calendar = inject(CalendarApi);
  private readonly router = inject(Router);
  private readonly toast = inject(MessageService);

  readonly steps = STEPS;
  readonly weekdays = LECTURE_WEEKDAYS;
  readonly roman = toRoman;
  readonly cycleOptions: Option<number>[] = CYCLES.map((cycle) => ({
    label: `Ciclo ${toRoman(cycle)}`,
    value: cycle,
  }));

  readonly step = signal(1);
  readonly file = signal<File | null>(null);
  readonly semester = signal<string | null>(null);
  readonly cycle = signal<number | null>(null);
  readonly preview = signal<ScheduleImportPreview | null>(null);
  readonly rows = signal<ScheduleImportRow[]>([]);
  readonly result = signal<ScheduleImportResult | null>(null);
  readonly onlyReview = signal(false);
  readonly loading = signal(false);
  readonly confirming = signal(false);
  readonly error = signal<string | null>(null);

  readonly semesters = signal<string[]>([]);
  readonly currentSemester = signal<string | null>(null);
  readonly teachers = signal<Option<number>[]>([]);
  readonly rooms = signal<Option<number>[]>([]);
  readonly defaultTeacherId = signal<number | null>(null);
  readonly defaultRoomId = signal<number | null>(null);
  readonly hourFrom = signal('07:00');
  readonly hourTo = signal('20:00');

  private nextRow = 0;

  readonly canRead = computed(
    () => this.file() !== null && this.semester() !== null && this.cycle() !== null && !this.loading(),
  );
  readonly canConfirm = computed(() => {
    if (this.rows().length === 0) return false;
    return this.rows().every(
      (row) => this.rowIssues(row).length === 0 && !this.pendingSuggestion(row),
    );
  });
  readonly reviewCount = computed(() => this.rows().filter((row) => this.needsReview(row)).length);
  readonly filteredRows = computed(() =>
    this.onlyReview() ? this.rows().filter((row) => this.needsReview(row)) : this.rows(),
  );
  readonly groups = computed<ScheduleImportGroup[]>(() =>
    groupScheduleImportRows(this.filteredRows()),
  );
  readonly typeLabel = computed(() => this.documentLabel(this.preview()?.tipo));

  constructor() {
    void this.loadContext();
  }

  private async loadContext(): Promise<void> {
    try {
      const [settings, semesterLabels, teacherPage, roomPage] = await Promise.all([
        this.calendar.settings().toPromise(),
        this.calendar.semesters().toPromise(),
        this.catalog.teachers({ page_size: 100 }).toPromise(),
        this.catalog.rooms({ page_size: 100 }).toPromise(),
      ]);
      const currentSemester = settings?.semester_label ?? null;
      this.currentSemester.set(currentSemester);
      this.semesters.set(
        [...new Set([currentSemester ?? '', ...(semesterLabels ?? [])])].filter(Boolean),
      );
      if (!this.semester()) {
        this.semester.set(currentSemester ?? semesterLabels?.[0] ?? null);
      }
      this.hourFrom.set(
        settings?.attendance_hour_start ? formatTime(settings.attendance_hour_start) : '07:00',
      );
      this.hourTo.set(
        settings?.attendance_hour_end ? formatTime(settings.attendance_hour_end) : '20:00',
      );
      this.teachers.set(
        (teacherPage?.items ?? []).map((teacher) => ({
          label: teacher.full_name,
          value: teacher.id,
        })),
      );
      this.rooms.set(
        (roomPage?.items ?? []).map((room) => ({ label: room.code, value: room.id })),
      );
    } catch (err) {
      this.toast.add({
        severity: 'warn',
        summary: 'Catálogos incompletos',
        detail: extractDetail(err),
        life: 4500,
      });
    }
  }

  onFile(file: File | null): void {
    this.file.set(file);
    this.preview.set(null);
    this.rows.set([]);
    this.result.set(null);
    this.error.set(null);
    if (this.step() !== 1) this.step.set(1);
  }

  onFileError(message: string): void {
    this.toast.add({ severity: 'error', summary: 'Archivo no válido', detail: message, life: 4500 });
  }

  async readSchedule(): Promise<void> {
    const file = this.file();
    if (!file || !this.semester() || !this.cycle()) {
      this.toast.add({
        severity: 'warn',
        summary: 'Falta contexto',
        detail: 'Elige el archivo, el periodo y el ciclo antes de leer el horario.',
        life: 3500,
      });
      return;
    }
    this.loading.set(true);
    this.error.set(null);
    try {
      const importPreview = await this.api.importSchedule(file).toPromise();
      if (!importPreview) return;
      this.preview.set(importPreview);
      this.nextRow = 0;
      this.rows.set(
        importPreview.bloques.map((block) => ({
          key: this.newKey(),
          course_code: (block.course_code ?? '').toUpperCase(),
          course_name: block.course_name ?? '',
          group_code: (block.group_code ?? '').toUpperCase(),
          teacher_id: block.teacher_id ?? null,
          room_id: block.room_id ?? null,
          teacher_name: block.teacher_name ?? null,
          room_code: block.room_code ?? null,
          course_suggestion: block.curso_sugerido ?? null,
          suggestion_dismissed: false,
          weekday: block.weekday,
          start_time: formatTime(block.start_time),
          end_time: formatTime(block.end_time),
          confiable: block.confiable,
          nota: block.nota,
          linea: block.linea,
          pagina: block.pagina,
        })),
      );
      this.onlyReview.set(importPreview.ambiguousos > 0);
      this.step.set(2);
      this.toast.add({
        severity: importPreview.ambiguousos > 0 ? 'warn' : 'success',
        summary: `${importPreview.total} bloque(s) detectado(s)`,
        detail:
          importPreview.ambiguousos > 0
            ? `${importPreview.ambiguousos} fila(s) necesitan revisión antes de guardar.`
            : 'Revisa los datos detectados; docente y aula son opcionales.',
        life: 4500,
      });
    } catch (err) {
      this.error.set(extractDetail(err));
      this.toast.add({
        severity: 'error',
        summary: 'No se pudo leer el horario',
        detail: extractDetail(err),
        life: 6000,
      });
    } finally {
      this.loading.set(false);
    }
  }

  updateRow(key: string, patch: Partial<ScheduleImportRow>): void {
    this.rows.update((rows) =>
      rows.map((row) =>
        row.key === key ? { ...row, ...patch, confiable: true, nota: null } : row,
      ),
    );
  }

  onCodeInput(key: string, event: Event, field: 'course_code' | 'group_code'): void {
    const value = (event.target as HTMLInputElement).value
      .toUpperCase()
      .replace(/[^A-Z0-9_-]/g, '');
    this.updateRow(
      key,
      field === 'course_code'
        ? { course_code: value, course_suggestion: null, suggestion_dismissed: true }
        : { group_code: value },
    );
  }

  pendingSuggestion(row: ScheduleImportRow): boolean {
    return row.course_suggestion != null && !row.suggestion_dismissed;
  }

  applyCourseSuggestion(row: ScheduleImportRow): void {
    const suggestion = row.course_suggestion;
    if (!suggestion) return;
    const original = row.course_code;
    this.rows.update((rows) =>
      rows.map((item) =>
        item.course_code === original
          ? {
              ...item,
              course_code: suggestion.code,
              course_name: suggestion.name,
              course_suggestion: null,
              suggestion_dismissed: true,
              confiable: true,
              nota: null,
            }
          : item,
      ),
    );
  }

  dismissCourseSuggestion(row: ScheduleImportRow): void {
    this.updateRow(row.key, { suggestion_dismissed: true });
  }

  onTextInput(key: string, event: Event): void {
    this.updateRow(key, { course_name: (event.target as HTMLInputElement).value });
  }

  onTimeInput(key: string, field: 'start_time' | 'end_time', event: Event): void {
    const value = (event.target as HTMLInputElement).value.slice(0, 5);
    this.updateRow(key, { [field]: value });
  }

  addRow(): void {
    this.rows.update((rows) => [
      ...rows,
      {
        key: this.newKey(),
        course_code: '',
        course_name: '',
        group_code: '',
        weekday: 1,
        start_time: '08:00',
        end_time: '10:00',
        teacher_id: null,
        room_id: null,
        teacher_name: null,
        room_code: null,
        course_suggestion: null,
        suggestion_dismissed: true,
        confiable: false,
        nota: 'Fila añadida a mano',
        linea: '',
        pagina: 1,
      },
    ]);
  }

  removeRow(key: string): void {
    this.rows.update((rows) => rows.filter((row) => row.key !== key));
  }

  rowIssues(row: ScheduleImportRow): string[] {
    return scheduleImportRowIssues(row, this.hourFrom(), this.hourTo());
  }

  needsReview(row: ScheduleImportRow): boolean {
    return (
      !row.confiable ||
      row.nota !== null ||
      this.rowIssues(row).length > 0 ||
      this.pendingSuggestion(row)
    );
  }

  groupNeedsReview(group: ImportGroup): boolean {
    return group.rows.some((row) => this.needsReview(row));
  }

  onReviewToggle(event: Event): void {
    this.onlyReview.set((event.target as HTMLInputElement).checked);
  }

  issuesText(row: ScheduleImportRow): string {
    return this.rowIssues(row).join(' · ');
  }

  goToStep(step: number): void {
    if (step === 1) {
      this.step.set(1);
    } else if (step === 2 && this.preview()) {
      this.step.set(2);
    }
  }

  async confirm(): Promise<void> {
    const teacherId = this.defaultTeacherId();
    const roomId = this.defaultRoomId();
    const cycle = this.cycle();
    const semester = this.semester();
    if (cycle === null || semester === null) {
      this.toast.add({
        severity: 'warn',
        summary: 'Completa la importación',
        detail: 'Indica el periodo y el ciclo antes de confirmar.',
        life: 4000,
      });
      return;
    }
    if (!this.canConfirm()) {
      this.toast.add({
        severity: 'warn',
        summary: 'Hay filas por corregir',
        detail: 'Revisa los bloques marcados en rojo antes de confirmar.',
        life: 4200,
      });
      return;
    }
    this.confirming.set(true);
    try {
      const importResult = await this.api
        .confirmScheduleImport({
          teacher_id: teacherId,
          room_id: roomId,
          cycle,
          semester_label: semester,
          bloques: this.rows().map((row) => ({
            course_code: row.course_code.trim().toUpperCase(),
            course_name: row.course_name.trim() || null,
            group_code: row.group_code.trim().toUpperCase(),
            weekday: row.weekday,
            start_time: formatTime(row.start_time),
            end_time: formatTime(row.end_time),
            teacher_id: row.teacher_id,
            room_id: row.room_id,
          })),
        })
        .toPromise();
      if (!importResult) return;
      this.result.set(importResult);
      this.step.set(3);
      this.toast.add({
        severity: 'success',
        summary: 'Horario importado',
        detail: `${importResult.bloques_creados} bloque(s) creados en ${importResult.grupos_creados.length} grupo(s).`,
        life: 4500,
      });
    } catch (err) {
      this.toast.add({
        severity: 'error',
        summary: 'No se pudo confirmar la importación',
        detail: extractDetail(err),
        life: 7000,
      });
    } finally {
      this.confirming.set(false);
    }
  }

  viewSchedule(): void {
    void this.router.navigate(['/admin/schedule'], {
      queryParams: { semester: this.semester(), cycle: this.cycle() },
    });
  }

  reset(): void {
    this.step.set(1);
    this.file.set(null);
    this.preview.set(null);
    this.rows.set([]);
    this.result.set(null);
    this.onlyReview.set(false);
    this.error.set(null);
  }

  private documentLabel(type: string | undefined): string {
    if (type === 'pdf_texto') return 'PDF con texto';
    if (type === 'pdf_ocr') return 'PDF escaneado (OCR)';
    if (type === 'imagen') return 'Foto (OCR)';
    return 'Documento';
  }

  private newKey(): string {
    this.nextRow += 1;
    return `block-${this.nextRow}`;
  }
}
