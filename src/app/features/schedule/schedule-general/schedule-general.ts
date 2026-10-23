import {
  ChangeDetectionStrategy,
  Component,
  CUSTOM_ELEMENTS_SCHEMA,
  computed,
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
import { CoursesApi } from '../../../core/services/courses-api';
import { CatalogApi } from '../../../core/services/catalog-api';
import { CalendarApi } from '../../../core/services/calendar-api';
import { AuthService } from '../../../core/services/auth/auth';
import { PageHeader } from '../../../shared/components/page-header/page-header';
import { UiButton } from '../../../shared/components/ui-button/ui-button';
import { UiAlert } from '../../../shared/components/ui-alert/ui-alert';
import { ModalDelete } from '../../../shared/components/modal-delete/modal-delete';
import {
  ScheduleEntry,
  ScheduleTable,
} from '../../../shared/components/schedule-table/schedule-table';
import { Group, ScheduleRow } from '../../../core/models/catalog';
import { CYCLES, toRoman } from '../../../shared/utils/cycles';
import {
  BLOCK_END_HOUR,
  BLOCK_START_HOUR,
  blockEndOptions,
  blockStartOptions,
  formatTime,
  hourValue,
  nextBlockEnd,
  validBlockRange,
} from '../../../shared/utils/schedule-hours';
import { LECTURE_WEEKDAYS, weekdayLabel } from '../../../shared/utils/weekdays';

interface Option<T> {
  label: string;
  value: T;
}

interface BlockForm {
  group_id: number | null;
  weekday: number;
  start_time: string;
  end_time: string;
  room_id: number | null;
  teacher_id: number | null;
}

@Component({
  selector: 'app-schedule-general-page',
  imports: [
    FormsModule, PageHeader, UiButton, UiAlert, ModalDelete,
    DialogModule, SelectModule, ScheduleTable,
  ],
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  templateUrl: './schedule-general.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ScheduleGeneralPage {
  protected readonly auth = inject(AuthService);
  private readonly api = inject(CoursesApi);
  private readonly catalog = inject(CatalogApi);
  private readonly calendar = inject(CalendarApi);
  private readonly qp = inject(QueryParams);
  private readonly toast = inject(MessageService);

  private readonly deleteModal = viewChild(ModalDelete);

  readonly weekdays = LECTURE_WEEKDAYS;
  readonly cycles = CYCLES;
  readonly roman = toRoman;
  readonly semester = this.qp.filter('semester');
  readonly cycleId = this.qp.number('cycle', 0);

  readonly semesters = signal<string[]>([]);
  readonly rows = signal<ScheduleRow[]>([]);
  readonly groups = signal<Group[]>([]);
  readonly courseOptions = signal<Option<number>[]>([]);
  readonly teacherOptions = signal<Option<number>[]>([]);
  readonly roomOptions = signal<Option<number>[]>([]);
  readonly loading = signal(false);
  readonly saving = signal(false);
  readonly deleting = signal(false);
  readonly error = signal<string | null>(null);

  readonly courseId = signal(0);
  readonly teacherId = signal(0);
  readonly roomId = signal(0);

  readonly attendanceStartTime = signal('07:00');
  readonly attendanceEndTime = signal('20:00');
  readonly scheduleHourRange = computed(() => ({
    from: Number(this.attendanceStartTime().slice(0, 2)),
    to: Number(this.attendanceEndTime().slice(0, 2)),
  }));

  readonly filtersActive = computed(
    () => this.courseId() !== 0 || this.teacherId() !== 0 || this.roomId() !== 0,
  );
  readonly cycleSelected = computed(() => this.cycleId() !== 0);

  readonly visibleRows = computed(() => {
    const cycle = this.cycleId();
    return cycle ? this.rows().filter((row) => row.cycle === cycle) : this.rows();
  });

  readonly cycleCounts = computed(() => {
    const counts = new Map<number, number>();
    for (const cycle of CYCLES) counts.set(cycle, 0);
    for (const row of this.rows()) {
      counts.set(row.cycle, (counts.get(row.cycle) ?? 0) + 1);
    }
    return counts;
  });

  readonly entries = computed<ScheduleEntry[]>(() =>
    this.visibleRows().map((row) => ({
      id: row.id,
      weekday: row.weekday,
      start_time: row.start_time,
      end_time: row.end_time,
      course_code: row.course_code,
      course_name: row.course_name,
      group_code: row.group_code,
      room_code: row.room_code,
      teacher_name: row.teacher_name,
    })),
  );

  readonly scheduledHours = computed(() =>
    this.visibleRows().reduce(
      (total, row) =>
        total + (this.timeToMinutes(row.end_time) - this.timeToMinutes(row.start_time)) / 60,
      0,
    ),
  );
  readonly availableHours = computed(() => {
    const hoursPerDay = this.scheduleHourRange().to - this.scheduleHourRange().from;
    return Math.max(0, hoursPerDay * LECTURE_WEEKDAYS.length - this.scheduledHours());
  });

  readonly groupOptions = computed<Option<number>[]>(() => {
    const cycle = this.cycleId();
    return this.groups()
      .filter((group) => !cycle || group.cycle === cycle)
      .map((group) => ({
        label: `${group.course_code} · Grupo ${group.group_code} · Ciclo ${this.roman(group.cycle)} · ${group.teacher_name ?? 'Sin docente'}`,
        value: group.id,
      }));
  });

  readonly blockForm = signal<BlockForm>({
    group_id: null,
    weekday: 1,
    start_time: '08:00',
    end_time: '10:00',
    room_id: null,
    teacher_id: null,
  });
  readonly editingBlockId = signal<number | null>(null);
  readonly startHours = blockStartOptions();
  readonly endHours = computed(() => blockEndOptions(this.blockForm().start_time));
  blockDialogVisible = false;

  readonly deleteTarget = signal<ScheduleRow | null>(null);
  deleteVisible = false;

  constructor() {
    this.courseId.set(this.qp.number('course', 0)());
    this.teacherId.set(this.qp.number('teacher', 0)());
    this.roomId.set(this.qp.number('room', 0)());
    void this.init();
  }

  private async init(): Promise<void> {
    await this.loadContext();
    await this.load();
  }

  private async loadContext(): Promise<void> {
    try {
      const [settings, semesterLabels, coursePage, teacherPage, roomPage] = await Promise.all([
        this.calendar.settings().toPromise(),
        this.calendar.semesters().toPromise(),
        this.api.courses({ page_size: 100 }).toPromise(),
        this.catalog.teachers({ page_size: 100 }).toPromise(),
        this.catalog.rooms({ page_size: 100 }).toPromise(),
      ]);
      const currentSemester = settings?.semester_label ?? null;
      this.semesters.set(
        [...new Set([currentSemester ?? '', ...(semesterLabels ?? [])])]
          .filter((semesterLabel) => semesterLabel !== ''),
      );
      if (!this.semester() && currentSemester) {
        await this.qp.update({ semester: currentSemester });
      }
      this.courseOptions.set(
        (coursePage?.items ?? []).map((course) => ({
          label: `${course.code} · ${course.name}`,
          value: course.id,
        })),
      );
      this.teacherOptions.set(
        (teacherPage?.items ?? []).map((teacher) => ({
          label: teacher.full_name,
          value: teacher.id,
        })),
      );
      this.roomOptions.set(
        (roomPage?.items ?? []).map((room) => ({ label: room.code, value: room.id })),
      );
      this.attendanceStartTime.set(
        settings?.attendance_hour_start ? formatTime(settings.attendance_hour_start) : '07:00',
      );
      this.attendanceEndTime.set(
        settings?.attendance_hour_end ? formatTime(settings.attendance_hour_end) : '20:00',
      );
    } catch (err) {
      this.toast.add({
        severity: 'warn',
        summary: 'Catálogos incompletos',
        detail: extractDetail(err),
        life: 4000,
      });
    }
  }

  async load(): Promise<void> {
    this.loading.set(true);
    this.error.set(null);
    try {
      const semester = this.semester();
      const [scheduleRows, groupList] = await Promise.all([
        this.api
          .schedule({
            semester: semester ?? undefined,
            course_id: this.courseId() || undefined,
            teacher_id: this.teacherId() || undefined,
            room_id: this.roomId() || undefined,
          })
          .toPromise(),
        this.api.groups({ semester: semester ?? undefined }).toPromise(),
      ]);
      this.rows.set(scheduleRows ?? []);
      this.groups.set(groupList ?? []);
    } catch (err) {
      this.error.set(extractDetail(err));
      this.rows.set([]);
    } finally {
      this.loading.set(false);
    }
  }

  onSemester(value: string | null): void {
    void this.qp.update({ semester: value });
    void this.load();
  }

  onCycle(value: number | null): void {
    void this.qp.update({ cycle: value });
  }

  tabClass(cycle: number | null): string {
    const active = cycle === null ? !this.cycleSelected() : this.cycleId() === cycle;
    return active
      ? 'flex shrink-0 items-center gap-1.5 rounded-lg bg-blue-50 px-3 py-1.5 text-xs font-semibold text-(--fareas-primary)'
      : 'flex shrink-0 items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium text-gray-500 transition-colors hover:bg-gray-50 hover:text-gray-800';
  }

  onCourse(value: number | null): void {
    this.courseId.set(value ?? 0);
    void this.qp.update({ course: value });
    void this.load();
  }

  onTeacher(value: number | null): void {
    this.teacherId.set(value ?? 0);
    void this.qp.update({ teacher: value });
    void this.load();
  }

  onRoom(value: number | null): void {
    this.roomId.set(value ?? 0);
    void this.qp.update({ room: value });
    void this.load();
  }

  clearFilters(): void {
    this.courseId.set(0);
    this.teacherId.set(0);
    this.roomId.set(0);
    void this.qp.update({ course: null, teacher: null, room: null });
    void this.load();
  }

  patchBlock(p: Partial<BlockForm>): void {
    this.blockForm.update((f) => ({ ...f, ...p }));
  }

  onStartTime(value: string): void {
    const currentEnd = this.blockForm().end_time;
    this.patchBlock({
      start_time: value,
      end_time: validBlockRange(value, currentEnd) ? currentEnd : nextBlockEnd(value),
    });
  }

  openCreateBlock(weekday?: number, hour?: number): void {
    const startTime = hour !== undefined ? this.formatHour(hour) : '08:00';
    this.editingBlockId.set(null);
    this.blockForm.set({
      group_id: null,
      weekday: weekday ?? 1,
      start_time: startTime,
      end_time: nextBlockEnd(startTime),
      room_id: this.roomId() || null,
      teacher_id: null,
    });
    this.blockDialogVisible = true;
  }

  openEditBlock(entry: ScheduleEntry): void {
    const row = this.rows().find((item) => item.id === entry.id);
    if (!row) return;
    this.editingBlockId.set(row.id);
    this.blockForm.set({
      group_id: row.group_id,
      weekday: row.weekday,
      start_time: formatTime(row.start_time),
      end_time: formatTime(row.end_time),
      room_id: row.room_id,
      teacher_id: row.teacher_id,
    });
    this.blockDialogVisible = true;
  }

  async onGroup(value: number | null): Promise<void> {
    const group = this.groups().find((item) => item.id === value);
    this.patchBlock({
      group_id: value,
      teacher_id: group?.teacher_id ?? null,
      room_id: value ? null : this.blockForm().room_id,
    });
    if (!value) return;
    try {
      const blocks = (await this.api.blocks(value).toPromise()) ?? [];
      const weekday = this.blockForm().weekday;
      const lastWeekdayBlock = blocks.filter((block) => block.weekday === weekday).at(-1);
      const lastBlock = blocks.at(-1);
      const roomId = lastWeekdayBlock?.room_id ?? lastBlock?.room_id ?? null;
      this.patchBlock({ room_id: roomId });
    } catch (err) {
      this.toast.add({
        severity: 'error',
        summary: 'No se pudo cargar el aula del grupo',
        detail: extractDetail(err),
        life: 4000,
      });
    }
  }

  async saveBlock(): Promise<void> {
    const form = this.blockForm();
    if (!form.group_id) {
      this.toast.add({ severity: 'warn', summary: 'Elige el grupo del bloque', life: 3000 });
      return;
    }
    if (!validBlockRange(form.start_time, form.end_time)) {
      this.toast.add({
        severity: 'warn',
        summary: 'Rango inválido',
        detail:
          'Elige horas exactas entre 07:00 y 20:00, sin minutos, con una duración máxima de 2 horas',
        life: 4500,
      });
      return;
    }
    const editingBlockId = this.editingBlockId();
    this.saving.set(true);
    try {
      if (editingBlockId !== null) {
        await this.api
          .updateBlock(editingBlockId, {
            weekday: Number(form.weekday),
            start_time: form.start_time,
            end_time: form.end_time,
            room_id: form.room_id,
            teacher_id: form.teacher_id,
          })
          .toPromise();
        this.toast.add({ severity: 'success', summary: 'Bloque actualizado', life: 2500 });
      } else {
        await this.api
          .createBlock(form.group_id, {
            weekday: Number(form.weekday),
            start_time: form.start_time,
            end_time: form.end_time,
            room_id: form.room_id,
            teacher_id: form.teacher_id,
          })
          .toPromise();
        this.toast.add({ severity: 'success', summary: 'Bloque añadido', life: 2500 });
      }
      this.blockDialogVisible = false;
      this.editingBlockId.set(null);
      await this.load();
    } catch (err) {
      this.toast.add({
        severity: 'error',
        summary: editingBlockId !== null
          ? 'No se pudo actualizar el bloque'
          : 'No se pudo añadir el bloque',
        detail: extractDetail(err),
        life: 6000,
      });
    } finally {
      this.saving.set(false);
    }
  }

  onBlockEdit(entry: ScheduleEntry): void {
    this.openEditBlock(entry);
  }

  onBlockRemove(entry: ScheduleEntry): void {
    const row = this.rows().find((scheduleRow) => scheduleRow.id === entry.id);
    if (row) {
      this.deleteTarget.set(row);
      this.deleteVisible = true;
    }
  }

  deleteLabel(): string | null {
    const row = this.deleteTarget();
    return row
      ? `${row.course_code} G${row.group_code} · ${weekdayLabel(row.weekday)} ${formatTime(row.start_time)}–${formatTime(row.end_time)}`
      : null;
  }

  async confirmDelete(): Promise<void> {
    const row = this.deleteTarget();
    if (!row) return;
    this.deleting.set(true);
    try {
      await this.api.deleteBlock(row.id).toPromise();
      this.toast.add({ severity: 'success', summary: 'Bloque eliminado', life: 2500 });
      await this.load();
    } catch (err) {
      this.toast.add({
        severity: 'error',
        summary: 'No se pudo quitar el bloque',
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

  protected formatHour(hour: number): string {
    return hourValue(Math.min(Math.max(hour, BLOCK_START_HOUR), BLOCK_END_HOUR - 1));
  }

  private timeToMinutes(value: string): number {
    const [hours, minutes] = formatTime(value).split(':').map(Number);
    return hours * 60 + (minutes || 0);
  }
}
