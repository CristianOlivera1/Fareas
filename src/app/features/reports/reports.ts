import {
  ChangeDetectionStrategy,
  Component,
  CUSTOM_ELEMENTS_SCHEMA,
  computed,
  effect,
  inject,
  signal,
  untracked,
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MessageService } from 'primeng/api';
import { SelectModule } from 'primeng/select';
import { firstValueFrom } from 'rxjs';

import type { Course, Group, Person, Room } from '../../core/models/catalog';
import { AuthService } from '../../core/services/auth/auth';
import { CalendarApi } from '../../core/services/calendar-api';
import { CatalogApi } from '../../core/services/catalog-api';
import { CoursesApi } from '../../core/services/courses-api';
import { ReportsApi } from '../../core/services/reports-api';
import type {
  ReportCatalogItem,
  ReportFormat,
  ReportPreview,
  ReportQuery,
  ReportTone,
} from '../../core/services/reports-api';
import { extractDetail } from '../../shared/utils/api-error';
import { CYCLES, toRoman } from '../../shared/utils/cycles';
import { presetRange } from '../../shared/utils/date-range';
import type { RangePreset } from '../../shared/utils/date-range';
import { saveBlob } from '../../shared/utils/download';
import { fetchAllPages } from '../../shared/utils/fetch-all';
import { PageHeader } from '../../shared/components/page-header/page-header';
import { UiButton } from '../../shared/components/ui-button/ui-button';

interface Option<T> {
  readonly label: string;
  readonly value: T;
}

const MATRIX_KEY = 'group-matrix';
const PREVIEW_DELAY_MS = 350;
const PERIOD_REPORTS = ['attendance', 'course-summary', 'student-summary'];

const MATRIX_REPORT: ReportCatalogItem = {
  key: MATRIX_KEY,
  title: 'Registro de asistencia del grupo',
  description: 'Matriz de alumnos por fecha con A (asistió), T (tardanza), F (falta) y FJ (falta justificada).',
  icon: 'material-symbols:grid-on-outline',
  formats: ['xlsx'],
  filters: ['grupo'],
};

const PRESETS: readonly Option<RangePreset>[] = [
  { label: 'Hoy', value: 'today' },
  { label: 'Esta semana', value: 'week' },
  { label: 'Este mes', value: 'month' },
  { label: 'Últimos 30 días', value: 'last30' },
  { label: 'Periodo vigente', value: 'semester' },
  { label: 'Personalizado', value: 'custom' },
];

const STATUSES: readonly Option<string>[] = [
  { label: 'Asistió', value: 'asistio' },
  { label: 'Tardanza', value: 'tardanza' },
  { label: 'Falta', value: 'falta' },
  { label: 'Falta justificada', value: 'falta_justificada' },
];

const FORMAT_LABELS: Record<ReportFormat, { label: string; icon: string }> = {
  pdf: { label: 'PDF', icon: 'material-symbols:picture-as-pdf-outline' },
  xlsx: { label: 'Excel', icon: 'material-symbols:table-chart-outline' },
  csv: { label: 'CSV', icon: 'material-symbols:csv-outline' },
};

const TONE_CLASSES: Record<ReportTone, string> = {
  ok: 'bg-green-50 text-green-700',
  warn: 'bg-amber-50 text-amber-700',
  bad: 'bg-red-50 text-red-700',
  info: 'bg-sky-50 text-sky-700',
  muted: 'bg-gray-50 text-gray-700',
};

const CELL_TONE_CLASSES: Record<ReportTone, string> = {
  ok: 'font-semibold text-green-700',
  warn: 'font-semibold text-amber-700',
  bad: 'font-semibold text-red-700',
  info: 'font-semibold text-sky-700',
  muted: 'text-gray-500',
};

@Component({
  selector: 'app-reports-page',
  imports: [FormsModule, SelectModule, PageHeader, UiButton],
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  templateUrl: './reports.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { class: 'block' },
})
export class ReportsPage {
  private readonly api = inject(ReportsApi);
  private readonly coursesApi = inject(CoursesApi);
  private readonly catalogApi = inject(CatalogApi);
  private readonly calendar = inject(CalendarApi);
  private readonly auth = inject(AuthService);
  private readonly toast = inject(MessageService);

  readonly presets = PRESETS;
  readonly statuses = STATUSES;
  readonly formatLabels = FORMAT_LABELS;
  readonly toneClass = (tone: ReportTone): string => TONE_CLASSES[tone];
  readonly cellClass = (tone: ReportTone | null): string => (tone ? CELL_TONE_CLASSES[tone] : '');

  readonly isTeacher = computed(() => this.auth.currentUser()?.role === 'docente');
  readonly reports = signal<ReportCatalogItem[]>([MATRIX_REPORT]);
  readonly selectedKey = signal('attendance');
  readonly selected = computed(
    () => this.reports().find((report) => report.key === this.selectedKey()) ?? this.reports()[0],
  );
  readonly isMatrix = computed(() => this.selectedKey() === MATRIX_KEY);

  readonly preset = signal<RangePreset>('last30');
  readonly from = signal('');
  readonly to = signal('');
  readonly cycle = signal<number | null>(null);
  readonly courseId = signal<number | null>(null);
  readonly groupId = signal<number | null>(null);
  readonly teacherId = signal<number | null>(null);
  readonly roomId = signal<number | null>(null);
  readonly chosenStatuses = signal<string[]>([]);
  readonly search = signal('');
  readonly onlyRisk = signal(false);
  readonly format = signal<ReportFormat>('pdf');

  readonly courses = signal<Course[]>([]);
  readonly groups = signal<Group[]>([]);
  readonly teachers = signal<Person[]>([]);
  readonly rooms = signal<Room[]>([]);
  private readonly semesterDates = signal<{ start: string | null; end: string | null } | null>(null);

  readonly preview = signal<ReportPreview | null>(null);
  readonly previewLoading = signal(false);
  readonly previewError = signal<string | null>(null);
  readonly downloading = signal(false);

  readonly cycleOptions: Option<number | null>[] = [
    { label: 'Todos los ciclos', value: null },
    ...CYCLES.map((cycle) => ({ label: `Ciclo ${toRoman(cycle)}`, value: cycle })),
  ];
  readonly courseOptions = computed<Option<number | null>[]>(() => [
    { label: 'Todos los cursos', value: null },
    ...this.courses()
      .filter((course) => this.cycle() === null || course.cycle === this.cycle())
      .map((course) => ({ label: `${course.code} · ${course.name}`, value: course.id })),
  ]);
  readonly groupOptions = computed<Option<number | null>[]>(() => {
    const options = this.groups()
      .filter((group) => this.courseId() === null || group.course_id === this.courseId())
      .filter((group) => this.cycle() === null || group.cycle === this.cycle())
      .map((group) => ({
        label: `${group.course_code} · Grupo ${group.group_code} · ${group.semester_label}`,
        value: group.id as number | null,
      }));
    return this.isMatrix() ? options : [{ label: 'Todos los grupos', value: null }, ...options];
  });
  readonly teacherOptions = computed<Option<number | null>[]>(() => [
    { label: 'Todos los docentes', value: null },
    ...this.teachers().map((teacher) => ({ label: teacher.full_name, value: teacher.id })),
  ]);
  readonly roomOptions = computed<Option<number | null>[]>(() => [
    { label: 'Todas las aulas', value: null },
    ...this.rooms().map((room) => ({ label: room.code, value: room.id })),
  ]);

  readonly rangeError = computed(() => {
    if (!this.usesPeriod()) return null;
    if (!this.from() || !this.to()) return 'Indica las dos fechas del periodo.';
    return this.from() > this.to() ? 'La fecha inicial no puede ser posterior a la final.' : null;
  });

  readonly query = computed<ReportQuery>(() => {
    const has = (filter: string) => this.selected().filters.includes(filter);
    return {
      desde: this.usesPeriod() ? this.from() : null,
      hasta: this.usesPeriod() ? this.to() : null,
      cycle: has('ciclo') ? this.cycle() : null,
      course_id: has('curso') ? this.courseId() : null,
      group_id: has('grupo') ? this.groupId() : null,
      teacher_id: has('docente') && !this.isTeacher() ? this.teacherId() : null,
      room_id: has('aula') ? this.roomId() : null,
      status: has('estado') && this.chosenStatuses().length > 0 ? this.chosenStatuses().join(',') : null,
      q: has('alumno') ? this.search().trim() || null : null,
      only_risk: has('riesgo') && this.onlyRisk() ? true : null,
    };
  });

  readonly activeFilters = computed(() => {
    const query = this.query();
    return [query.cycle, query.course_id, query.group_id, query.teacher_id, query.room_id, query.status, query.q, query.only_risk]
      .filter((value) => value !== null && value !== undefined).length;
  });

  readonly canDownload = computed(() => {
    if (this.rangeError() || this.downloading()) return false;
    return this.isMatrix() ? this.groupId() !== null : true;
  });

  constructor() {
    this.applyPreset('last30');
    void this.loadCatalogs();

    effect((onCleanup) => {
      const key = this.selectedKey();
      const query = this.query();
      const blocked = this.rangeError() !== null || key === MATRIX_KEY;
      if (blocked) {
        untracked(() => this.preview.set(null));
        return;
      }
      const timer = setTimeout(() => void this.loadPreview(key, query), PREVIEW_DELAY_MS);
      onCleanup(() => clearTimeout(timer));
    });
  }

  has(filter: string): boolean {
    return this.selected().filters.includes(filter);
  }

  usesPeriod(): boolean {
    return PERIOD_REPORTS.includes(this.selectedKey());
  }

  select(key: string): void {
    this.selectedKey.set(key);
    const available = this.selected().formats;
    if (!available.includes(this.format())) this.format.set(available[0]);
    if (key === MATRIX_KEY && this.groupId() === null) {
      const first = this.groups()[0];
      if (first) this.groupId.set(first.id);
    }
  }

  applyPreset(preset: RangePreset): void {
    this.preset.set(preset);
    if (preset === 'custom') return;
    const range = presetRange(preset, new Date(), this.semesterDates());
    this.from.set(range.from);
    this.to.set(range.to);
  }

  onDate(field: 'from' | 'to', value: string): void {
    (field === 'from' ? this.from : this.to).set(value);
    this.preset.set('custom');
  }

  onCycle(value: number | null): void {
    this.cycle.set(value);
    this.dropStale();
  }

  onCourse(value: number | null): void {
    this.courseId.set(value);
    this.dropStale();
  }

  toggleStatus(status: string): void {
    this.chosenStatuses.update((current) =>
      current.includes(status) ? current.filter((item) => item !== status) : [...current, status],
    );
  }

  clearFilters(): void {
    this.cycle.set(null);
    this.courseId.set(null);
    this.groupId.set(this.isMatrix() ? this.groupId() : null);
    this.teacherId.set(null);
    this.roomId.set(null);
    this.chosenStatuses.set([]);
    this.search.set('');
    this.onlyRisk.set(false);
  }

  async download(): Promise<void> {
    if (!this.canDownload()) return;
    this.downloading.set(true);
    try {
      const request = this.isMatrix()
        ? this.api.groupMatrix(this.groupId() as number)
        : this.api.export(this.selectedKey(), this.format(), this.query());
      const file = await new Promise<{ blob: Blob; filename: string }>((resolve, reject) =>
        request.subscribe({ next: resolve, error: reject }),
      );
      saveBlob(file.blob, file.filename);
      this.toast.add({ severity: 'success', summary: 'Reporte descargado', detail: file.filename, life: 3000 });
    } catch (err) {
      this.toast.add({
        severity: 'error',
        summary: 'No se pudo generar el reporte',
        detail: extractDetail(await this.readBlobError(err)),
        life: 4500,
      });
    } finally {
      this.downloading.set(false);
    }
  }

  private dropStale(): void {
    const group = this.groups().find((item) => item.id === this.groupId());
    const stale =
      group !== undefined &&
      ((this.courseId() !== null && group.course_id !== this.courseId()) ||
        (this.cycle() !== null && group.cycle !== this.cycle()));
    if (stale) this.groupId.set(null);
    const course = this.courses().find((item) => item.id === this.courseId());
    if (course && this.cycle() !== null && course.cycle !== this.cycle()) this.courseId.set(null);
  }

  private async loadPreview(key: string, query: ReportQuery): Promise<void> {
    this.previewLoading.set(true);
    this.previewError.set(null);
    try {
      const result = await firstValueFrom(this.api.preview(key, query));
      if (key === this.selectedKey()) this.preview.set(result);
    } catch (err) {
      this.preview.set(null);
      this.previewError.set(extractDetail(err));
    } finally {
      this.previewLoading.set(false);
    }
  }

  private async loadCatalogs(): Promise<void> {
    const teacher = this.isTeacher();
    const [catalog, settings, courses, groups, teachers, rooms] = await Promise.allSettled([
      firstValueFrom(this.api.catalog()),
      firstValueFrom(this.calendar.settings()),
      fetchAllPages((params) => this.coursesApi.courses(params)),
      firstValueFrom(this.coursesApi.groups()),
      teacher ? Promise.resolve([]) : fetchAllPages((params) => this.catalogApi.teachers(params)),
      fetchAllPages((params) => this.catalogApi.rooms(params)),
    ]);
    if (catalog.status === 'fulfilled') this.reports.set([...catalog.value, MATRIX_REPORT]);
    else this.fail('No se pudo cargar el catálogo de reportes', catalog.reason);
    if (settings.status === 'fulfilled') {
      this.semesterDates.set({
        start: settings.value.semester_start,
        end: settings.value.semester_end,
      });
    }
    if (courses.status === 'fulfilled') this.courses.set(courses.value);
    if (groups.status === 'fulfilled') this.groups.set(this.ownGroups(groups.value));
    if (teachers.status === 'fulfilled') this.teachers.set(teachers.value as Person[]);
    if (rooms.status === 'fulfilled') this.rooms.set(rooms.value);
  }

  private ownGroups(groups: Group[]): Group[] {
    const userId = this.auth.currentUser()?.id;
    return this.isTeacher() ? groups.filter((group) => group.teacher_id === userId) : groups;
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

  private fail(summary: string, err: unknown): void {
    this.toast.add({ severity: 'error', summary, detail: extractDetail(err), life: 4500 });
  }
}
