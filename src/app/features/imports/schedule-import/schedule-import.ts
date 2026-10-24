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
import { firstValueFrom } from 'rxjs';
import type { Observable } from 'rxjs';

import { PageHeader } from '../../../shared/components/page-header/page-header';
import { UiAlert } from '../../../shared/components/ui-alert/ui-alert';
import { UiButton } from '../../../shared/components/ui-button/ui-button';
import { FileDrop } from '../../../shared/components/file-drop/file-drop';
import { CoursesApi } from '../../../core/services/courses-api';
import { CatalogApi } from '../../../core/services/catalog-api';
import { CalendarApi } from '../../../core/services/calendar-api';
import type { Page } from '../../../core/api/api-url';
import type { Course, Person, Room } from '../../../core/models/catalog';
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
import { matchRooms } from '../../../shared/utils/room-match';
import { compactText, rankBySimilarity, similarity } from '../../../shared/utils/similarity';

interface Option<T> {
  readonly label: string;
  readonly value: T;
}

export interface CourseInfo {
  readonly registered: Course | null;
  readonly suggestion: Course | null;
}

export interface RowHints {
  readonly teachers: Option<number>[];
  readonly rooms: Option<number>[];
}

const STEPS = [
  { number: 1, label: 'Archivo y contexto' },
  { number: 2, label: 'Revisar bloques' },
  { number: 3, label: 'Resultado' },
];

const PAGE_SIZE = 100;
const COURSE_SUGGESTION_MIN = 0.7;
const NAME_HINT_MIN = 0.6;
const NO_HINTS: RowHints = { teachers: [], rooms: [] };

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
  readonly loading = signal(false);
  readonly confirming = signal(false);
  readonly error = signal<string | null>(null);

  readonly courses = signal<Course[]>([]);
  readonly teacherList = signal<Person[]>([]);
  readonly roomList = signal<Room[]>([]);
  readonly defaultTeacherId = signal<number | null>(null);
  readonly defaultRoomId = signal<number | null>(null);
  readonly keptAsNew = signal<ReadonlySet<string>>(new Set());
  readonly hourFrom = signal('07:00');
  readonly hourTo = signal('20:00');

  private nextRow = 0;

  readonly courseOptions = computed<Option<number>[]>(() =>
    this.courses().map((course) => ({ label: `${course.code} · ${course.name}`, value: course.id })),
  );
  readonly teachers = computed<Option<number>[]>(() =>
    this.teacherList().map((teacher) => ({ label: teacher.full_name, value: teacher.id })),
  );
  readonly rooms = computed<Option<number>[]>(() =>
    this.roomList().map((room) => ({ label: room.code, value: room.id })),
  );
  readonly groups = computed<ScheduleImportGroup[]>(() => groupScheduleImportRows(this.rows()));
  readonly courseInfos = computed(() => {
    const catalog = this.courses();
    return new Map(
      this.groups().map((group) => [group.code, this.resolveCourse(group, catalog)] as const),
    );
  });
  readonly rowHints = computed(() => {
    const teachers = this.teacherList();
    const rooms = this.roomList();
    const hints = new Map<string, RowHints>();
    for (const row of this.rows()) {
      const missingTeacher = row.teacher_id === null && row.teacher_name;
      const missingRoom = row.room_id === null && row.room_code;
      if (!missingTeacher && !missingRoom) continue;
      hints.set(row.key, {
        teachers: missingTeacher
          ? rankBySimilarity(row.teacher_name, teachers, (item) => item.full_name, {
              min: NAME_HINT_MIN,
              limit: 2,
            }).map((entry) => ({ label: entry.item.full_name, value: entry.item.id }))
          : [],
        rooms: missingRoom
          ? matchRooms(row.room_code, rooms).map((room) => ({ label: room.code, value: room.id }))
          : [],
      });
    }
    return hints;
  });

  readonly canRead = computed(
    () => this.file() !== null && this.semester() !== null && this.cycle() !== null && !this.loading(),
  );
  readonly pendingGroups = computed(
    () => this.groups().filter((group) => this.pendingSuggestion(group)).length,
  );
  readonly canConfirm = computed(() => {
    if (this.rows().length === 0) return false;
    return this.pendingGroups() === 0 && this.rows().every((row) => this.rowIssues(row).length === 0);
  });
  readonly reviewCount = computed(() => this.rows().filter((row) => this.needsReview(row)).length);
  readonly typeLabel = computed(() => this.documentLabel(this.preview()?.tipo));

  constructor() {
    void this.loadContext();
  }

  private async fetchAll<T>(
    load: (params: { page_size: number; page?: number }) => Observable<Page<T>>,
  ): Promise<T[]> {
    const first = await firstValueFrom(load({ page_size: PAGE_SIZE }));
    const items = [...first.items];
    const pages = Math.ceil(first.total / PAGE_SIZE);
    for (let page = 2; page <= pages; page += 1) {
      const next = await firstValueFrom(load({ page_size: PAGE_SIZE, page }));
      items.push(...next.items);
    }
    return items;
  }

  private async loadContext(): Promise<void> {
    try {
      const [settings, teachers, rooms, courses] = await Promise.all([
        firstValueFrom(this.calendar.settings()),
        this.fetchAll((params) => this.catalog.teachers(params)),
        this.fetchAll((params) => this.catalog.rooms(params)),
        this.fetchAll((params) => this.api.courses(params)),
      ]);
      this.semester.set(settings?.semester_label ?? null);
      this.hourFrom.set(
        settings?.attendance_hour_start ? formatTime(settings.attendance_hour_start) : '07:00',
      );
      this.hourTo.set(
        settings?.attendance_hour_end ? formatTime(settings.attendance_hour_end) : '20:00',
      );
      this.teacherList.set(teachers);
      this.roomList.set(rooms);
      this.courses.set(courses);
    } catch (err) {
      this.toast.add({
        severity: 'warn',
        summary: 'Catálogos incompletos',
        detail: extractDetail(err),
        life: 4500,
      });
    }
  }

  private resolveCourse(group: ScheduleImportGroup, catalog: readonly Course[]): CourseInfo {
    const code = compactText(group.code);
    const registered = catalog.find((course) => compactText(course.code) === code) ?? null;
    if (registered) return { registered, suggestion: null };
    const name = group.rows.find((row) => row.course_name.trim())?.course_name ?? '';
    const best = catalog
      .map((course) => ({
        course,
        score: Math.max(similarity(group.code, course.code), similarity(name, course.name) * 0.95),
      }))
      .filter((entry) => entry.score >= COURSE_SUGGESTION_MIN)
      .sort((a, b) => b.score - a.score)[0];
    return { registered: null, suggestion: best?.course ?? null };
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
      const importPreview = await firstValueFrom(this.api.importSchedule(file));
      this.preview.set(importPreview);
      this.nextRow = 0;
      this.keptAsNew.set(new Set());
      this.rows.set(
        importPreview.bloques.map((block) => ({
          key: this.newKey(),
          course_code: (block.course_code ?? '').toUpperCase(),
          course_name: block.course_name ?? '',
          group_code: (block.group_code ?? '').toUpperCase(),
          teacher_id: block.teacher_id ?? this.defaultTeacherId(),
          room_id: block.room_id ?? this.defaultRoomId(),
          teacher_manual: block.teacher_id != null,
          room_manual: block.room_id != null,
          teacher_name: block.teacher_name ?? null,
          room_code: block.room_code ?? null,
          weekday: block.weekday,
          start_time: formatTime(block.start_time),
          end_time: formatTime(block.end_time),
          confiable: block.confiable,
          nota: block.nota,
          linea: block.linea,
          pagina: block.pagina,
        })),
      );
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
    this.updateRow(key, { [field]: value });
  }

  onTextInput(key: string, event: Event): void {
    this.updateRow(key, { course_name: (event.target as HTMLInputElement).value });
  }

  onTimeInput(key: string, field: 'start_time' | 'end_time', event: Event): void {
    const value = (event.target as HTMLInputElement).value.slice(0, 5);
    this.updateRow(key, { [field]: value });
  }

  onDefaultTeacher(id: number | null): void {
    this.defaultTeacherId.set(id);
    this.rows.update((rows) =>
      rows.map((row) => (row.teacher_manual ? row : { ...row, teacher_id: id })),
    );
  }

  onDefaultRoom(id: number | null): void {
    this.defaultRoomId.set(id);
    this.rows.update((rows) =>
      rows.map((row) => (row.room_manual ? row : { ...row, room_id: id })),
    );
  }

  onRowTeacher(key: string, id: number | null): void {
    this.updateRow(key, {
      teacher_id: id ?? this.defaultTeacherId(),
      teacher_manual: id !== null,
    });
  }

  onRowRoom(key: string, id: number | null): void {
    this.updateRow(key, {
      room_id: id ?? this.defaultRoomId(),
      room_manual: id !== null,
    });
  }

  courseInfo(group: ScheduleImportGroup): CourseInfo {
    return this.courseInfos().get(group.code) ?? { registered: null, suggestion: null };
  }

  pendingSuggestion(group: ScheduleImportGroup): boolean {
    return this.courseInfo(group).suggestion !== null && !this.keptAsNew().has(group.code);
  }

  chooseCourse(group: ScheduleImportGroup, courseId: number | null): void {
    const course = this.courses().find((item) => item.id === courseId);
    if (!course) return;
    const keys = new Set(group.rows.map((row) => row.key));
    this.rows.update((rows) =>
      rows.map((row) =>
        keys.has(row.key)
          ? { ...row, course_code: course.code, course_name: course.name, confiable: true, nota: null }
          : row,
      ),
    );
  }

  applyCourseSuggestion(group: ScheduleImportGroup): void {
    const suggestion = this.courseInfo(group).suggestion;
    if (suggestion) this.chooseCourse(group, suggestion.id);
  }

  keepAsNewCourse(group: ScheduleImportGroup): void {
    this.keptAsNew.update((kept) => new Set(kept).add(group.code));
  }

  hintsFor(row: ScheduleImportRow): RowHints {
    return this.rowHints().get(row.key) ?? NO_HINTS;
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
        teacher_id: this.defaultTeacherId(),
        room_id: this.defaultRoomId(),
        teacher_manual: false,
        room_manual: false,
        teacher_name: null,
        room_code: null,
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
    return !row.confiable || this.rowIssues(row).length > 0;
  }

  groupNeedsReview(group: ScheduleImportGroup): boolean {
    return this.pendingSuggestion(group) || group.rows.some((row) => this.needsReview(row));
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
        detail: 'Revisa los bloques marcados y resuelve las sugerencias de curso antes de confirmar.',
        life: 4200,
      });
      return;
    }
    this.confirming.set(true);
    try {
      const importResult = await firstValueFrom(
        this.api.confirmScheduleImport({
          teacher_id: this.defaultTeacherId(),
          room_id: this.defaultRoomId(),
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
        }),
      );
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
    this.keptAsNew.set(new Set());
    this.error.set(null);
  }

  private documentLabel(type: string | undefined): string {
    if (type === 'pdf_texto') return 'PDF con texto';
    if (type === 'pdf_ocr') return 'PDF escaneado';
    if (type === 'imagen') return 'Imagen';
    return 'Documento';
  }

  private newKey(): string {
    this.nextRow += 1;
    return `block-${this.nextRow}`;
  }
}
