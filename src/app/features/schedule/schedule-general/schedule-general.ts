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
import { UiInput } from '../../../shared/components/ui-input/ui-input';
import { UiAlert } from '../../../shared/components/ui-alert/ui-alert';
import { ModalDelete } from '../../../shared/components/modal-delete/modal-delete';
import {
  ScheduleEntry,
  ScheduleTable,
} from '../../../shared/components/schedule-table/schedule-table';
import { Group, ScheduleRow } from '../../../core/models/catalog';

const DIAS = [
  { label: 'Lunes', value: 1 },
  { label: 'Martes', value: 2 },
  { label: 'Miércoles', value: 3 },
  { label: 'Jueves', value: 4 },
  { label: 'Viernes', value: 5 },
];

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
}

@Component({
  selector: 'app-schedule-general-page',
  imports: [
    FormsModule, PageHeader, UiButton, UiInput, UiAlert, ModalDelete,
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

  readonly dias = DIAS;
  readonly semester = this.qp.filter('semester');

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

  /** RF-01: franja de clases del sistema (Parámetros, 07:00–20:00 por defecto). */
  readonly horaInicio = signal('07:00');
  readonly horaFin = signal('20:00');
  readonly franja = computed(() => ({
    from: Number(this.horaInicio().slice(0, 2)),
    to: Number(this.horaFin().slice(0, 2)),
  }));

  readonly filtersActive = computed(
    () => this.courseId() !== 0 || this.teacherId() !== 0 || this.roomId() !== 0,
  );

  readonly entries = computed<ScheduleEntry[]>(() =>
    this.rows().map((r) => ({
      id: r.id,
      weekday: r.weekday,
      start_time: r.start_time,
      end_time: r.end_time,
      course_code: r.course_code,
      course_name: r.course_name,
      group_code: r.group_code,
      room_code: r.room_code,
      teacher_name: r.teacher_name,
    })),
  );

  readonly ocupadas = computed(() =>
    this.rows().reduce(
      (total, r) => total + (this.minutos(r.end_time) - this.minutos(r.start_time)) / 60,
      0,
    ),
  );
  readonly libres = computed(() => {
    const porDia = this.franja().to - this.franja().from;
    return Math.max(0, porDia * DIAS.length - this.ocupadas());
  });

  readonly groupOptions = computed<Option<number>[]>(() =>
    this.groups().map((g) => ({
      label: `${g.course_code} · Grupo ${g.group_code} · ${g.teacher_name}`,
      value: g.id,
    })),
  );

  readonly blockForm = signal<BlockForm>({
    group_id: null,
    weekday: 1,
    start_time: '08:00',
    end_time: '10:00',
    room_id: null,
  });
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
      const [cfg, labels, courses, teachers, rooms] = await Promise.all([
        this.calendar.settings().toPromise(),
        this.calendar.semesters().toPromise(),
        this.api.courses({ page_size: 100 }).toPromise(),
        this.catalog.teachers({ page_size: 100 }).toPromise(),
        this.catalog.rooms({ page_size: 100 }).toPromise(),
      ]);
      const vigente = cfg?.semester_label ?? null;
      this.semesters.set([...new Set([vigente ?? '', ...(labels ?? [])])].filter((s) => s !== ''));
      if (!this.semester() && vigente) {
        await this.qp.update({ semester: vigente });
      }
      this.courseOptions.set(
        (courses?.items ?? []).map((c) => ({ label: `${c.code} · ${c.name}`, value: c.id })),
      );
      this.teacherOptions.set(
        (teachers?.items ?? []).map((t) => ({ label: t.full_name, value: t.id })),
      );
      this.roomOptions.set((rooms?.items ?? []).map((r) => ({ label: r.code, value: r.id })));
      this.horaInicio.set(this.hora(cfg?.attendance_hour_start) ?? '07:00');
      this.horaFin.set(this.hora(cfg?.attendance_hour_end) ?? '20:00');
    } catch (err) {
      this.toast.add({
        severity: 'warn',
        summary: 'Catálogos incompletos',
        detail: extractDetail(err),
        life: 4000,
      });
    }
  }

  /** Datos de la rejilla. Las horas se filtran en el SERVIDOR: si filtras por
   * un aula, las celdas vacías son huecos reales de esa aula. */
  async load(): Promise<void> {
    this.loading.set(true);
    this.error.set(null);
    try {
      const sem = this.semester();
      const [rows, groups] = await Promise.all([
        this.api
          .schedule({
            semester: sem ?? undefined,
            course_id: this.courseId() || undefined,
            teacher_id: this.teacherId() || undefined,
            room_id: this.roomId() || undefined,
          })
          .toPromise(),
        this.api.groups({ semester: sem ?? undefined }).toPromise(),
      ]);
      this.rows.set(rows ?? []);
      this.groups.set(groups ?? []);
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

  openCreateBlock(weekday?: number, hour?: number): void {
    const inicio = hour !== undefined ? this.hhmm(hour) : '08:00';
    this.blockForm.set({
      group_id: null,
      weekday: weekday ?? 1,
      start_time: inicio,
      end_time: this.addHours(inicio, 2),
      room_id: this.roomId() || null,
    });
    this.blockDialogVisible = true;
  }

  /** Al elegir grupo: se prellena el aula de su último bloque (ese día si lo
   * hay, si no el último de la semana). Se consulta al servidor porque con
   * filtros activos la rejilla puede no traer todos sus bloques. */
  async onGroup(value: number | null): Promise<void> {
    this.patchBlock({ group_id: value, room_id: value ? null : this.blockForm().room_id });
    if (!value) return;
    try {
      const blocks = (await this.api.blocks(value).toPromise()) ?? [];
      const dia = this.blockForm().weekday;
      const delDia = blocks.filter((b) => b.weekday === dia).at(-1);
      const ultimo = blocks.at(-1);
      const room = delDia?.room_id ?? ultimo?.room_id ?? null;
      this.patchBlock({ room_id: room });
    } catch {
      // Sin bloques previos no hay aula que sugerir: el selector queda abierto.
    }
  }

  async saveBlock(): Promise<void> {
    const f = this.blockForm();
    if (!f.group_id) {
      this.toast.add({ severity: 'warn', summary: 'Elige el grupo del bloque', life: 3000 });
      return;
    }
    if (!f.room_id) {
      this.toast.add({ severity: 'warn', summary: 'Indica el aula del bloque', life: 3000 });
      return;
    }
    if (!f.start_time || !f.end_time || f.start_time >= f.end_time) {
      this.toast.add({
        severity: 'warn',
        summary: 'Rango inválido',
        detail: 'La hora de fin debe ser posterior al inicio',
        life: 3500,
      });
      return;
    }
    if (f.start_time < this.horaInicio() || f.end_time > this.horaFin()) {
      this.toast.add({
        severity: 'warn',
        summary: 'Fuera de la franja de clases',
        detail: `Las clases van de ${this.horaInicio()} a ${this.horaFin()}`,
        life: 4000,
      });
      return;
    }
    this.saving.set(true);
    try {
      await this.api
        .createBlock(f.group_id, {
          weekday: Number(f.weekday),
          start_time: f.start_time,
          end_time: f.end_time,
          room_id: f.room_id,
        })
        .toPromise();
      this.toast.add({ severity: 'success', summary: 'Bloque añadido', life: 2500 });
      this.blockDialogVisible = false;
      await this.load();
    } catch (err) {
      // RF-06: choque de aula o de docente (409) con el detalle del backend.
      this.toast.add({
        severity: 'error',
        summary: 'No se pudo añadir el bloque',
        detail: extractDetail(err),
        life: 6000,
      });
    } finally {
      this.saving.set(false);
    }
  }

  onBlockRemove(entry: ScheduleEntry): void {
    const row = this.rows().find((r) => r.id === entry.id);
    if (row) {
      this.deleteTarget.set(row);
      this.deleteVisible = true;
    }
  }

  deleteLabel(): string | null {
    const r = this.deleteTarget();
    return r
      ? `${r.course_code} G${r.group_code} · ${DIAS[r.weekday - 1]?.label ?? r.weekday} ${this.time(r.start_time)}–${this.time(r.end_time)}`
      : null;
  }

  async confirmDelete(): Promise<void> {
    const r = this.deleteTarget();
    if (!r) return;
    this.deleting.set(true);
    try {
      await this.api.deleteBlock(r.id).toPromise();
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

  time(value: string): string {
    return value.slice(0, 5);
  }

  protected hhmm(hour: number): string {
    return `${String(hour).padStart(2, '0')}:00`;
  }

  private hora(value: string | null | undefined): string | null {
    return value ? value.slice(0, 5) : null;
  }

  private minutos(value: string): number {
    const [h, m] = value.slice(0, 5).split(':').map(Number);
    return h * 60 + (m || 0);
  }

  /** Fin propuesto: nunca se pasa del cierre de la franja. */
  private addHours(time: string, hours: number): string {
    const total = Math.min(this.minutos(this.horaFin()), this.minutos(time) + hours * 60);
    const hh = String(Math.floor(total / 60)).padStart(2, '0');
    const mm = String(total % 60).padStart(2, '0');
    return `${hh}:${mm}`;
  }
}
