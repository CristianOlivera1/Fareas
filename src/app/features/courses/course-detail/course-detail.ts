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
import { Block, Group } from '../../../core/models/catalog';

const DIAS = [
  { label: 'Lunes', value: 1 },
  { label: 'Martes', value: 2 },
  { label: 'Miércoles', value: 3 },
  { label: 'Jueves', value: 4 },
  { label: 'Viernes', value: 5 },
  { label: 'Sábado', value: 6 },
  { label: 'Domingo', value: 7 },
];

interface Option<T> {
  label: string;
  value: T;
}

interface GroupForm {
  group_code: string;
  teacher_id: number | null;
  room_id: number | null;
  capacity: number;
}

interface BlockForm {
  weekday: number;
  start_time: string;
  end_time: string;
}

type DeleteTarget = { kind: 'group'; group: Group } | { kind: 'block'; block: Block } | null;

/** F2 · Detalle de curso: grupos (R9 con cupo y semestre) y su horario
 * semanal con validación de choques RF-06 (el 409 del backend se muestra
 * tal cual). Solo admin escribe; docente ve en modo lectura. */
@Component({
  selector: 'app-course-detail-page',
  imports: [
    FormsModule, PageHeader, UiButton, UiInput, UiAlert, ModalDelete,
    DialogModule, SelectModule,
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

  readonly dias = DIAS;

  readonly semester = this.qp.filter('semester');

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

  readonly groupForm = signal<GroupForm>({
    group_code: '',
    teacher_id: null,
    room_id: null,
    capacity: 40,
  });
  readonly blockForm = signal<BlockForm>({ weekday: 1, start_time: '08:00', end_time: '10:00' });

  groupDialogVisible = false;
  blockDialogVisible = false;
  deleteVisible = false;
  readonly deleteTarget = signal<DeleteTarget>(null);

  readonly selectedGroup = computed(() =>
    this.groups().find((g) => g.id === this.selectedGroupId()) ?? null,
  );

  readonly title = computed(() => {
    const first = this.groups()[0];
    const code = this.queryCode || first?.course_code || `#${this.courseId}`;
    const name = this.queryName || first?.course_name || '';
    return name ? `${code} · ${name}` : code;
  });

  readonly selectedGroupBlocks = computed(() =>
    [...this.blocks()].sort((a, b) => a.weekday - b.weekday || a.start_time.localeCompare(b.start_time)),
  );

  constructor() {
    void this.init();
  }

  // --- Lectura -------------------------------------------------------------
  private async init(): Promise<void> {
    await this.loadContext();
    await this.loadGroups();
  }

  private async loadContext(): Promise<void> {
    try {
      const [cfg, labels, teachers, rooms] = await Promise.all([
        this.calendar.settings().toPromise(),
        this.calendar.semesters().toPromise(),
        this.catalog.teachers({ page_size: 100 }).toPromise(),
        this.catalog.rooms({ page_size: 100 }).toPromise(),
      ]);
      const vigente = cfg?.semester_label ?? null;
      const opciones = [...new Set([vigente ?? '', ...(labels ?? [])])].filter((s) => s !== '');
      this.semesters.set(opciones);
      if (!this.semester() && vigente) {
        // Fija el semestre vigente en la URL para que el refresco lo conserve.
        await this.qp.update({ semester: vigente });
      }
      this.teacherOptions.set(
        (teachers?.items ?? []).map((t) => ({ label: t.full_name, value: t.id })),
      );
      this.roomOptions.set((rooms?.items ?? []).map((r) => ({ label: r.code, value: r.id })));
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
    const sem = semesterOverride ?? this.semester();
    this.loading.set(true);
    this.error.set(null);
    try {
      const list = await this.api.courseGroups(this.courseId, sem).toPromise();
      const grupos = list ?? [];
      this.groups.set(grupos);
      const actual = this.selectedGroupId();
      if (!grupos.some((g) => g.id === actual)) {
        this.selectedGroupId.set(grupos[0]?.id ?? null);
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
      const list = await this.api.blocks(groupId).toPromise();
      this.blocks.set(list ?? []);
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

  /** Tarjeta del grupo: borde azul cuando es el grupo seleccionado. */
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
    return this.selectedGroupBlocks().filter((b) => b.weekday === weekday);
  }

  time(value: string): string {
    return value.slice(0, 5);
  }

  dayLabel(weekday: number): string {
    return DIAS.find((d) => d.value === weekday)?.label ?? `Día ${weekday}`;
  }

  cupoPercent(group: Group): number {
    return group.capacity > 0
      ? Math.min(100, Math.round((group.enrolled_count / group.capacity) * 100))
      : 0;
  }

  cupoClass(group: Group): string {
    const pct = this.cupoPercent(group);
    if (group.enrolled_count >= group.capacity) return 'bg-red-500';
    return pct >= 80 ? 'bg-amber-500' : 'bg-green-500';
  }

  goBack(): void {
    void this.router.navigate(['..'], { relativeTo: this.route });
  }

  // --- Grupos (R9) ---------------------------------------------------------
  patch(p: Partial<GroupForm>): void {
    this.groupForm.update((f) => ({ ...f, ...p }));
  }

  openCreateGroup(): void {
    this.groupForm.set({ group_code: '', teacher_id: null, room_id: null, capacity: 40 });
    this.groupDialogVisible = true;
  }

  async saveGroup(): Promise<void> {
    const f = this.groupForm();
    if (!f.group_code.trim() || !f.teacher_id || !f.room_id) {
      this.toast.add({
        severity: 'warn',
        summary: 'Completa el grupo',
        detail: 'Grupo, docente y aula son obligatorios',
        life: 3500,
      });
      return;
    }
    this.saving.set(true);
    try {
      await this.api
        .createGroup(this.courseId, {
          group_code: f.group_code.trim().toUpperCase(),
          teacher_id: f.teacher_id,
          room_id: f.room_id,
          capacity: Number(f.capacity) || 40,
        })
        .toPromise();
      this.toast.add({
        severity: 'success',
        summary: 'Grupo creado',
        detail: 'Añade ahora sus bloques de horario',
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

  // --- Bloques (RF-06) -----------------------------------------------------
  patchBlock(p: Partial<BlockForm>): void {
    this.blockForm.update((f) => ({ ...f, ...p }));
  }

  openCreateBlock(weekday?: number): void {
    const group = this.selectedGroup();
    const sugeridas = this.blocksFor(weekday ?? 1);
    const ultimo = sugeridas[sugeridas.length - 1];
    this.blockForm.set({
      weekday: weekday ?? 1,
      start_time: ultimo ? this.time(ultimo.end_time) : '08:00',
      end_time: ultimo ? this.addHours(this.time(ultimo.end_time), 2) : '10:00',
    });
    if (!group) {
      this.toast.add({
        severity: 'warn',
        summary: 'Selecciona un grupo',
        detail: 'El horario pertenece a un grupo concreto',
        life: 3000,
      });
      return;
    }
    this.blockDialogVisible = true;
  }

  async saveBlock(): Promise<void> {
    const group = this.selectedGroup();
    if (!group) return;
    const f = this.blockForm();
    if (!f.start_time || !f.end_time) {
      this.toast.add({ severity: 'warn', summary: 'Indica hora de inicio y de fin', life: 3000 });
      return;
    }
    if (f.start_time >= f.end_time) {
      this.toast.add({
        severity: 'warn',
        summary: 'Rango inválido',
        detail: 'La hora de fin debe ser posterior al inicio',
        life: 3500,
      });
      return;
    }
    this.saving.set(true);
    try {
      await this.api
        .createBlock(group.id, {
          weekday: Number(f.weekday),
          start_time: f.start_time,
          end_time: f.end_time,
        })
        .toPromise();
      this.toast.add({ severity: 'success', summary: 'Bloque añadido', life: 2500 });
      this.blockDialogVisible = false;
      await this.loadBlocks(group.id);
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

  // --- Bajas (grupo / bloque) ---------------------------------------------
  askDeleteGroup(group: Group): void {
    this.deleteTarget.set({ kind: 'group', group });
    this.deleteVisible = true;
  }

  askDeleteBlock(block: Block): void {
    this.deleteTarget.set({ kind: 'block', block });
    this.deleteVisible = true;
  }

  deleteLabel(): string | null {
    const t = this.deleteTarget();
    if (!t) return null;
    return t.kind === 'group'
      ? `grupo ${t.group.group_code}`
      : `${this.dayLabel(t.block.weekday)} ${this.time(t.block.start_time)}–${this.time(t.block.end_time)}`;
  }

  deleteEntity(): string {
    return this.deleteTarget()?.kind === 'group' ? 'grupo' : 'bloque';
  }

  deleteSoft(): boolean {
    return this.deleteTarget()?.kind === 'group';
  }

  deleteWarning(): string | null {
    const t = this.deleteTarget();
    if (!t || t.kind !== 'group') return null;
    return t.group.enrolled_count > 0
      ? `El grupo tiene ${t.group.enrolled_count} alumno(s) matriculado(s): conservarán su historial, pero el grupo dejará de abrir sesiones.`
      : null;
  }

  cancelDelete(): void {
    this.deleteTarget.set(null);
    this.deleteVisible = false;
  }

  async confirmDelete(): Promise<void> {
    const t = this.deleteTarget();
    if (!t) return;
    this.deleting.set(true);
    try {
      if (t.kind === 'group') {
        await this.api.deactivateGroup(t.group.id).toPromise();
        this.toast.add({ severity: 'success', summary: 'Grupo desactivado', life: 2500 });
        this.selectedGroupId.set(null);
        await this.loadGroups();
      } else {
        await this.api.deleteBlock(t.block.id).toPromise();
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

  private addHours(time: string, hours: number): string {
    const [h, m] = time.split(':').map(Number);
    const total = Math.min(23 * 60 + 59, h * 60 + m + hours * 60);
    const hh = String(Math.floor(total / 60)).padStart(2, '0');
    const mm = String(total % 60).padStart(2, '0');
    return `${hh}:${mm}`;
  }
}
