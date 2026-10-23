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
import {
  ScheduleImportPreview,
  ScheduleImportResult,
  ScheduleImportRow,
} from '../../../core/models/imports';

interface Option<T> {
  readonly label: string;
  readonly value: T;
}

interface ImportGroup {
  readonly code: string;
  readonly name: string;
  readonly rows: ScheduleImportRow[];
}

const DAYS: Option<number>[] = [
  { label: 'Lunes', value: 1 },
  { label: 'Martes', value: 2 },
  { label: 'Miércoles', value: 3 },
  { label: 'Jueves', value: 4 },
  { label: 'Viernes', value: 5 },
];

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
  readonly days = DAYS;
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
    if (this.defaultTeacherId() === null || this.defaultRoomId() === null) return false;
    return this.rows().every((row) => this.rowIssues(row).length === 0);
  });
  readonly reviewCount = computed(() => this.rows().filter((row) => this.needsReview(row)).length);
  readonly filteredRows = computed(() =>
    this.onlyReview() ? this.rows().filter((row) => this.needsReview(row)) : this.rows(),
  );
  readonly groups = computed<ImportGroup[]>(() => {
    const grouped = new Map<string, ScheduleImportRow[]>();
    const sorted = [...this.filteredRows()].sort(
      (a, b) =>
        a.course_code.localeCompare(b.course_code) ||
        a.group_code.localeCompare(b.group_code) ||
        a.weekday - b.weekday ||
        a.start_time.localeCompare(b.start_time),
    );
    for (const row of sorted) {
      const code = row.course_code.trim().toUpperCase() || 'SIN CURSO';
      const rows = grouped.get(code) ?? [];
      rows.push(row);
      grouped.set(code, rows);
    }
    return [...grouped.entries()].map(([code, rows]) => ({
      code,
      name: rows.find((row) => row.course_name.trim())?.course_name.trim() ?? 'Curso sin nombre',
      rows,
    }));
  });
  readonly typeLabel = computed(() => this.documentLabel(this.preview()?.tipo));

  constructor() {
    void this.loadContext();
  }

  private async loadContext(): Promise<void> {
    try {
      const [cfg, labels, teachers, rooms] = await Promise.all([
        this.calendar.settings().toPromise(),
        this.calendar.semesters().toPromise(),
        this.catalog.teachers({ page_size: 100 }).toPromise(),
        this.catalog.rooms({ page_size: 100 }).toPromise(),
      ]);
      const current = cfg?.semester_label ?? null;
      this.currentSemester.set(current);
      this.semesters.set([...new Set([current ?? '', ...(labels ?? [])].filter(Boolean))]);
      if (!this.semester()) this.semester.set(current ?? labels?.[0] ?? null);
      this.hourFrom.set(cfg?.attendance_hour_start?.slice(0, 5) ?? '07:00');
      this.hourTo.set(cfg?.attendance_hour_end?.slice(0, 5) ?? '20:00');
      this.teachers.set(
        (teachers?.items ?? []).map((teacher) => ({ label: teacher.full_name, value: teacher.id })),
      );
      this.rooms.set(
        (rooms?.items ?? []).map((room) => ({ label: room.code, value: room.id })),
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
      const preview = await this.api.importSchedule(file).toPromise();
      if (!preview) return;
      this.preview.set(preview);
      this.nextRow = 0;
      this.rows.set(
        preview.bloques.map((block) => ({
          key: this.newKey(),
          course_code: (block.course_code ?? '').toUpperCase(),
          course_name: block.course_name ?? '',
          group_code: (block.group_code ?? '').toUpperCase(),
          weekday: block.weekday,
          start_time: block.start_time.slice(0, 5),
          end_time: block.end_time.slice(0, 5),
          teacher_id: null,
          room_id: null,
          confiable: block.confiable,
          nota: block.nota,
          linea: block.linea,
          pagina: block.pagina,
        })),
      );
      this.onlyReview.set(preview.ambiguousos > 0);
      this.step.set(2);
      this.toast.add({
        severity: preview.ambiguousos > 0 ? 'warn' : 'success',
        summary: `${preview.total} bloque(s) detectado(s)`,
        detail:
          preview.ambiguousos > 0
            ? `${preview.ambiguousos} fila(s) necesitan revisión antes de guardar.`
            : 'Revisa y asigna el docente y el aula de cada bloque.',
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
    this.updateRow(key, field === 'course_code' ? { course_code: value } : { group_code: value });
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
    const issues: string[] = [];
    const code = row.course_code.trim();
    const group = row.group_code.trim();
    if (code.length < 3 || code.length > 20) issues.push('Código de curso de 3 a 20 caracteres');
    if (group.length < 1 || group.length > 5) issues.push('Grupo de 1 a 5 caracteres');
    if (!Number.isInteger(row.weekday) || row.weekday < 1 || row.weekday > 5) {
      issues.push('Día de lunes a viernes');
    }
    const start = this.minutes(row.start_time);
    const end = this.minutes(row.end_time);
    const from = this.minutes(this.hourFrom());
    const to = this.minutes(this.hourTo());
    if (start === null || end === null) {
      issues.push('Hora de inicio y fin válidas');
    } else {
      if (start >= end) issues.push('La hora de inicio debe ser menor que la de fin');
      if (end - start > 120) issues.push('El bloque no puede durar más de 2 horas');
      if (from !== null && start < from) issues.push(`La clase empieza antes de ${this.hourFrom()}`);
      if (to !== null && end > to) issues.push(`La clase termina después de ${this.hourTo()}`);
    }
    return issues;
  }

  needsReview(row: ScheduleImportRow): boolean {
    return !row.confiable || row.nota !== null || this.rowIssues(row).length > 0;
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

  dayLabel(weekday: number): string {
    return DAYS.find((day) => day.value === weekday)?.label ?? `Día ${weekday}`;
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
    if (teacherId === null || roomId === null || cycle === null || semester === null) {
      this.toast.add({
        severity: 'warn',
        summary: 'Completa la importación',
        detail: 'Indica el docente y el aula por defecto, además del periodo y el ciclo.',
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
      const result = await this.api
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
            start_time: row.start_time.slice(0, 5),
            end_time: row.end_time.slice(0, 5),
            teacher_id: row.teacher_id,
            room_id: row.room_id,
          })),
        })
        .toPromise();
      if (!result) return;
      this.result.set(result);
      this.step.set(3);
      this.toast.add({
        severity: 'success',
        summary: 'Horario importado',
        detail: `${result.bloques_creados} bloque(s) creados en ${result.grupos_creados.length} grupo(s).`,
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

  private minutes(value: string): number | null {
    const match = /^(\d{2}):(\d{2})/.exec(value);
    if (!match) return null;
    const hours = Number(match[1]);
    const minutes = Number(match[2]);
    if (hours > 23 || minutes > 59) return null;
    return hours * 60 + minutes;
  }
}
