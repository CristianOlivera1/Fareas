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
import { ActivatedRoute, Router } from '@angular/router';
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
import { UiInput } from '../../../shared/components/ui-input/ui-input';
import { UiAlert } from '../../../shared/components/ui-alert/ui-alert';
import { ModalDelete } from '../../../shared/components/modal-delete/modal-delete';
import {
  ScheduleEntry,
  ScheduleTable,
} from '../../../shared/components/schedule-table/schedule-table';
import { Block, Group } from '../../../core/models/catalog';
import { cycleLabel, toRoman } from '../../../shared/utils/cycles';
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

interface GroupForm {
  group_code: string;
  teacher_id: number | null;
  capacity: number;
}

interface BlockForm {
  weekday: number;
  start_time: string;
  end_time: string;
  room_id: number | null;
  teacher_id: number | null;
}

type DeleteTarget = { kind: 'group'; group: Group } | { kind: 'block'; block: Block } | null;

@Component({
  selector: 'app-course-detail-page',
  imports: [
    FormsModule, PageHeader, UiButton, UiInput, UiAlert, ModalDelete,
    DialogModule, SelectModule, ScheduleTable,
  ],
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  templateUrl: './course-detail.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class CourseDetailPage {
  protected readonly auth = inject(AuthService);
  private readonly api = inject(CoursesApi);
  private readonly catalog = inject(CatalogApi);
  private readonly calendar = inject(CalendarApi);
  private readonly qp = inject(QueryParams);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly toast = inject(MessageService);

  private readonly deleteModal = viewChild(ModalDelete);

  readonly courseId = Number(this.route.snapshot.paramMap.get('courseId'));
  private readonly queryCode = (this.route.snapshot.queryParamMap.get('code') ?? '').trim();
  private readonly queryName = (this.route.snapshot.queryParamMap.get('name') ?? '').trim();
  private readonly queryCycle = Number(this.route.snapshot.queryParamMap.get('cycle') ?? 0);

  readonly weekdays = LECTURE_WEEKDAYS;
  readonly roman = toRoman;

  readonly semester = this.qp.filter('semester');

  readonly currentSemester = signal<string | null>(null);
  readonly semesters = signal<string[]>([]);
  readonly groups = signal<Group[]>([]);
  readonly blocks = signal<Block[]>([]);
  readonly selectedGroupId = signal<number | null>(null);
  readonly loading = signal(false);
  readonly blocksLoading = signal(false);
  readonly error = signal<string | null>(null);
  readonly saving = signal(false);
  readonly deleting = signal(false);

  readonly teacherOptions = signal<Option<number>[]>([]);
  readonly roomOptions = signal<Option<number>[]>([]);

  readonly attendanceStartTime = signal('07:00');
  readonly attendanceEndTime = signal('20:00');
  readonly scheduleHourRange = computed(() => ({
    from: Number(this.attendanceStartTime().slice(0, 2)),
    to: Number(this.attendanceEndTime().slice(0, 2)),
  }));

  readonly groupForm = signal<GroupForm>({
    group_code: '',
    teacher_id: null,
    capacity: 40,
  });
  readonly blockForm = signal<BlockForm>({
    weekday: 1,
    start_time: '08:00',
    end_time: '10:00',
    room_id: null,
    teacher_id: null,
  });
  readonly editingBlockId = signal<number | null>(null);
  readonly startHours = blockStartOptions();
  readonly endHours = computed(() => blockEndOptions(this.blockForm().start_time));

  groupDialogVisible = false;
  blockDialogVisible = false;
  deleteVisible = false;
  readonly deleteTarget = signal<DeleteTarget>(null);

  readonly selectedGroup = computed(() =>
    this.groups().find((group) => group.id === this.selectedGroupId()) ?? null,
  );

  readonly title = computed(() => {
    const firstGroup = this.groups()[0];
    const courseCode = this.queryCode || firstGroup?.course_code || `#${this.courseId}`;
    const courseName = this.queryName || firstGroup?.course_name || '';
    return courseName ? `${courseCode} · ${courseName}` : courseCode;
  });

  readonly courseCycle = computed(() => {
    const firstGroup = this.groups()[0];
    const cycle = firstGroup?.cycle ?? this.queryCycle;
    return cycle >= 1 && cycle <= 10 ? cycle : null;
  });

  readonly subtitle = computed(() => {
    const cycle = this.courseCycle();
    return cycle
      ? `${cycleLabel(cycle)} · grupos, capacidad y horarios semanales`
      : 'Grupos, capacidad y horarios semanales';
  });

  readonly isCurrentPeriod = computed(() => {
    const selectedSemester = this.semester();
    const currentSemester = this.currentSemester();
    return !selectedSemester || !currentSemester || selectedSemester === currentSemester;
  });

  readonly selectedGroupBlocks = computed(() =>
    [...this.blocks()].sort(
      (firstBlock, secondBlock) =>
        firstBlock.weekday - secondBlock.weekday ||
        firstBlock.start_time.localeCompare(secondBlock.start_time),
    ),
  );

  readonly scheduleEntries = computed<ScheduleEntry[]>(() => {
    const group = this.selectedGroup();
    if (!group) return [];
    return this.blocks().map((block) => ({
      id: block.id,
      weekday: block.weekday,
      start_time: block.start_time,
      end_time: block.end_time,
      course_code: group.course_code,
      course_name: group.course_name,
      group_code: group.group_code,
      room_code: block.room_code,
      teacher_name: group.teacher_name,
    }));
  });

  constructor() {
    void this.init();
  }

  private async init(): Promise<void> {
    await this.loadContext();
    await this.loadGroups();
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
      const semesterOptions = [
        ...new Set([currentSemester ?? '', ...(semesterLabels ?? []), this.semester() ?? '']),
      ].filter((semesterLabel) => semesterLabel !== '');
      this.currentSemester.set(currentSemester);
      this.semesters.set(semesterOptions);
      if (!this.semester() && currentSemester) {
        await this.qp.update({ semester: currentSemester });
      }
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

  private async loadGroups(semesterOverride?: string | null): Promise<void> {
    const semester = semesterOverride ?? this.semester();
    this.loading.set(true);
    this.error.set(null);
    try {
      const groupList = await this.api.courseGroups(this.courseId, semester).toPromise();
      const groups = groupList ?? [];
      this.groups.set(groups);
      const selectedGroupId = this.selectedGroupId();
      if (!groups.some((group) => group.id === selectedGroupId)) {
        this.selectedGroupId.set(groups[0]?.id ?? null);
      }
      if (this.selectedGroupId() !== null) {
        await this.loadBlocks(this.selectedGroupId() as number);
      } else {
        this.blocks.set([]);
      }
    } catch (err) {
      this.error.set(extractDetail(err));
    } finally {
      this.loading.set(false);
    }
  }

  private async loadBlocks(groupId: number): Promise<void> {
    this.blocksLoading.set(true);
    try {
      const blockList = await this.api.blocks(groupId).toPromise();
      this.blocks.set(blockList ?? []);
    } catch (err) {
      this.toast.add({
        severity: 'error',
        summary: 'No se pudo cargar el horario',
        detail: extractDetail(err),
        life: 4000,
      });
      this.blocks.set([]);
    } finally {
      this.blocksLoading.set(false);
    }
  }

  reloadGroups(): void {
    void this.loadGroups();
  }

  cardClass(group: Group): string {
    return group.id === this.selectedGroupId()
      ? 'border-(--fareas-primary) ring-1 ring-(--fareas-primary)'
      : 'border-gray-200';
  }

  onSemester(value: string | null): void {
    void this.qp.update({ semester: value });
    this.selectedGroupId.set(null);
    this.blocks.set([]);
    void this.loadGroups(value);
  }

  selectGroup(group: Group): void {
    this.selectedGroupId.set(group.id);
    void this.loadBlocks(group.id);
  }

  blocksFor(weekday: number): Block[] {
    return this.selectedGroupBlocks().filter((block) => block.weekday === weekday);
  }

  onBlockAdd(event: { weekday: number; hour: number }): void {
    this.openCreateBlock(event.weekday, this.formatHour(event.hour));
  }

  onBlockRemove(entry: ScheduleEntry): void {
    const block = this.blocks().find((candidate) => candidate.id === entry.id);
    if (block) this.askDeleteBlock(block);
  }

  onBlockEdit(entry: ScheduleEntry): void {
    const block = this.blocks().find((candidate) => candidate.id === entry.id);
    if (!block) return;
    this.editingBlockId.set(block.id);
    this.blockForm.set({
      weekday: block.weekday,
      start_time: formatTime(block.start_time),
      end_time: formatTime(block.end_time),
      room_id: block.room_id,
      teacher_id: block.teacher_id ?? this.selectedGroup()?.teacher_id ?? null,
    });
    this.blockDialogVisible = true;
  }

  capacityPercent(group: Group): number {
    return group.capacity > 0
      ? Math.min(100, Math.round((group.enrolled_count / group.capacity) * 100))
      : 0;
  }

  capacityClass(group: Group): string {
    const percentage = this.capacityPercent(group);
    if (group.enrolled_count >= group.capacity) return 'bg-red-500';
    return percentage >= 80 ? 'bg-amber-500' : 'bg-green-500';
  }

  goBack(): void {
    void this.router.navigate(['..'], { relativeTo: this.route });
  }

  patch(p: Partial<GroupForm>): void {
    this.groupForm.update((form) => ({ ...form, ...p }));
  }

  readonly allGroupsFull = computed(
    () => this.groups().length > 0 && this.groups().every((group) => group.enrolled_count >= group.capacity),
  );

  readonly nextGroupCode = computed(() => {
    const used = new Set(this.groups().map((group) => group.group_code.toUpperCase()));
    for (let code = 65; code <= 90; code += 1) {
      const letter = String.fromCharCode(code);
      if (!used.has(letter)) return letter;
    }
    return '';
  });

  openCreateGroup(): void {
    this.groupForm.set({ group_code: this.nextGroupCode(), teacher_id: null, capacity: 40 });
    this.groupDialogVisible = true;
  }

  readonly teacherGroup = signal<Group | null>(null);
  readonly teacherChoice = signal<number | null>(null);
  teacherDialogVisible = false;

  openTeacher(group: Group): void {
    this.teacherGroup.set(group);
    this.teacherChoice.set(group.teacher_id);
    this.teacherDialogVisible = true;
  }

  async saveTeacher(): Promise<void> {
    const group = this.teacherGroup();
    if (!group) return;
    this.saving.set(true);
    try {
      await this.api.updateGroup(group.id, { teacher_id: this.teacherChoice() }).toPromise();
      this.toast.add({
        severity: 'success',
        summary: this.teacherChoice() ? 'Docente asignado' : 'Docente retirado',
        life: 3000,
      });
      this.teacherDialogVisible = false;
      await this.loadGroups();
    } catch (err) {
      this.toast.add({
        severity: 'error',
        summary: 'No se pudo actualizar el docente',
        detail: extractDetail(err),
        life: 5500,
      });
    } finally {
      this.saving.set(false);
    }
  }

  async saveGroup(): Promise<void> {
    const form = this.groupForm();
    if (!form.group_code.trim()) {
      this.toast.add({
        severity: 'warn',
        summary: 'Completa el grupo',
        detail: 'El código del grupo es obligatorio; el docente puedes asignarlo después',
        life: 3500,
      });
      return;
    }
    this.saving.set(true);
    try {
      await this.api
        .createGroup(this.courseId, {
          group_code: form.group_code.trim().toUpperCase(),
          teacher_id: form.teacher_id,
          capacity: Number(form.capacity) || 40,
        })
        .toPromise();
      this.toast.add({
        severity: 'success',
        summary: 'Grupo creado',
        detail: 'Añade sus bloques de horario y asígnale docente cuando lo tengas',
        life: 3500,
      });
      this.groupDialogVisible = false;
      await this.loadGroups();
    } catch (err) {
      this.toast.add({
        severity: 'error',
        summary: 'No se pudo crear el grupo',
        detail: extractDetail(err),
        life: 5000,
      });
    } finally {
      this.saving.set(false);
    }
  }

  patchBlock(p: Partial<BlockForm>): void {
    this.blockForm.update((form) => ({ ...form, ...p }));
  }

  onStartTime(value: string): void {
    const currentEnd = this.blockForm().end_time;
    this.patchBlock({
      start_time: value,
      end_time: validBlockRange(value, currentEnd) ? currentEnd : nextBlockEnd(value),
    });
  }

  openCreateBlock(weekday?: number, hour?: string): void {
    const group = this.selectedGroup();
    const weekdayBlocks = this.blocksFor(weekday ?? 1);
    const lastWeekdayBlock = weekdayBlocks[weekdayBlocks.length - 1];
    const previousEndTime = lastWeekdayBlock ? formatTime(lastWeekdayBlock.end_time) : null;
    const startTime = hour ?? previousEndTime ?? '08:00';
    this.editingBlockId.set(null);
    this.blockForm.set({
      weekday: weekday ?? 1,
      start_time: startTime,
      end_time: nextBlockEnd(startTime),
      room_id: lastWeekdayBlock?.room_id ?? this.blocks().at(-1)?.room_id ?? null,
      teacher_id: group?.teacher_id ?? null,
    });
    this.blockDialogVisible = true;
  }

  async saveBlock(): Promise<void> {
    const group = this.selectedGroup();
    const form = this.blockForm();
    if (!form.start_time || !form.end_time) {
      this.toast.add({ severity: 'warn', summary: 'Indica hora de inicio y de fin', life: 3000 });
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
      } else if (group) {
        await this.api
          .createBlock(group.id, {
            weekday: Number(form.weekday),
            start_time: form.start_time,
            end_time: form.end_time,
            room_id: form.room_id,
            teacher_id: form.teacher_id,
          })
          .toPromise();
        this.toast.add({ severity: 'success', summary: 'Bloque añadido', life: 2500 });
      } else {
        await this.api
          .createCourseBlock(this.courseId, {
            weekday: Number(form.weekday),
            start_time: form.start_time,
            end_time: form.end_time,
            room_id: form.room_id,
            teacher_id: form.teacher_id,
          })
          .toPromise();
        this.toast.add({
          severity: 'success',
          summary: 'Curso añadido al horario',
          detail: 'Se creó el grupo A sin docente; puedes asignarlo cuando lo tengas',
          life: 4500,
        });
      }
      this.blockDialogVisible = false;
      this.editingBlockId.set(null);
      if (group) await this.loadBlocks(group.id);
      else await this.loadGroups();
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

  askDeleteGroup(group: Group): void {
    this.deleteTarget.set({ kind: 'group', group });
    this.deleteVisible = true;
  }

  askDeleteBlock(block: Block): void {
    this.deleteTarget.set({ kind: 'block', block });
    this.deleteVisible = true;
  }

  deleteLabel(): string | null {
    const target = this.deleteTarget();
    if (!target) return null;
    return target.kind === 'group'
      ? `grupo ${target.group.group_code}`
      : `${weekdayLabel(target.block.weekday)} ${formatTime(target.block.start_time)}–${formatTime(target.block.end_time)}`;
  }

  deleteEntity(): string {
    return this.deleteTarget()?.kind === 'group' ? 'grupo' : 'bloque';
  }

  deleteSoft(): boolean {
    return this.deleteTarget()?.kind === 'group';
  }

  deleteWarning(): string | null {
    const target = this.deleteTarget();
    if (!target || target.kind !== 'group') return null;
    return target.group.enrolled_count > 0
      ? `El grupo tiene ${target.group.enrolled_count} alumno(s) matriculado(s): conservarán su historial, pero el grupo dejará de abrir sesiones.`
      : null;
  }

  cancelDelete(): void {
    this.deleteTarget.set(null);
    this.deleteVisible = false;
  }

  async reactivateGroup(group: Group): Promise<void> {
    this.saving.set(true);
    try {
      await this.api.activateGroup(group.id).toPromise();
      this.toast.add({
        severity: 'success',
        summary: `Grupo ${group.group_code} reactivado`,
        detail: 'Vuelve a abrir sesiones con sus bloques de siempre',
        life: 3500,
      });
      await this.loadGroups();
    } catch (err) {
      this.toast.add({
        severity: 'error',
        summary: 'No se pudo reactivar el grupo',
        detail: extractDetail(err),
        life: 4500,
      });
    } finally {
      this.saving.set(false);
    }
  }

  async confirmDelete(): Promise<void> {
    const target = this.deleteTarget();
    if (!target) return;
    this.deleting.set(true);
    try {
      if (target.kind === 'group') {
        await this.api.deactivateGroup(target.group.id).toPromise();
        this.toast.add({ severity: 'success', summary: 'Grupo desactivado', life: 2500 });
        this.selectedGroupId.set(null);
        await this.loadGroups();
      } else {
        await this.api.deleteBlock(target.block.id).toPromise();
        this.toast.add({ severity: 'success', summary: 'Bloque eliminado', life: 2500 });
        const groupId = this.selectedGroupId();
        if (groupId !== null) await this.loadBlocks(groupId);
      }
    } catch (err) {
      this.toast.add({
        severity: 'error',
        summary: 'No se pudo completar la acción',
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

  private formatHour(hour: number): string {
    return hourValue(Math.min(Math.max(hour, BLOCK_START_HOUR), BLOCK_END_HOUR - 1));
  }
}
