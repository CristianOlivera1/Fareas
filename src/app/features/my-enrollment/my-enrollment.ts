import {
  ChangeDetectionStrategy,
  Component,
  CUSTOM_ELEMENTS_SCHEMA,
  computed,
  inject,
  signal,
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MessageService } from 'primeng/api';
import { firstValueFrom, Observable } from 'rxjs';

import {
  EnrollmentBlock,
  EnrollmentStatus,
  OfferGroup,
  SelectionOutcome,
} from '../../core/models/enrollment';
import { EnrollmentApi } from '../../core/services/enrollment-api';
import { extractDetail } from '../../shared/utils/api-error';
import { toRoman } from '../../shared/utils/cycles';
import { blocksLabel } from '../../shared/utils/weekdays';
import { PageHeader } from '../../shared/components/page-header/page-header';
import { UiAlert } from '../../shared/components/ui-alert/ui-alert';
import { UiButton } from '../../shared/components/ui-button/ui-button';
import { UiInput } from '../../shared/components/ui-input/ui-input';

export interface CourseOffer {
  readonly courseId: number;
  readonly code: string;
  readonly name: string;
  readonly cycle: number;
  readonly groups: OfferGroup[];
  readonly current: OfferGroup | null;
  readonly pending: boolean;
}

type Choice = number | null;

function overlap(a: EnrollmentBlock, b: EnrollmentBlock): boolean {
  return a.weekday === b.weekday && a.start_time < b.end_time && b.start_time < a.end_time;
}

@Component({
  selector: 'app-my-enrollment-page',
  imports: [FormsModule, PageHeader, UiAlert, UiButton, UiInput],
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  templateUrl: './my-enrollment.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { class: 'block' },
})
export class MyEnrollmentPage {
  private readonly api = inject(EnrollmentApi);
  private readonly toast = inject(MessageService);

  readonly roman = toRoman;
  readonly blocksLabel = blocksLabel;

  readonly status = signal<EnrollmentStatus | null>(null);
  readonly offer = signal<OfferGroup[]>([]);
  readonly loading = signal(true);
  readonly error = signal<string | null>(null);
  readonly busy = signal<number | null>(null);
  readonly confirmingWithdraw = signal<number | null>(null);
  readonly cycle = signal<number>(1);
  readonly query = signal('');
  readonly selection = signal<Record<number, Choice>>({});
  readonly confirming = signal(false);
  readonly outcome = signal<SelectionOutcome | null>(null);

  readonly open = computed(() => this.status()?.window.open ?? false);

  readonly allCourses = computed<CourseOffer[]>(() => {
    const byCourse = new Map<number, { base: OfferGroup; groups: OfferGroup[]; current: OfferGroup | null; pending: boolean }>();
    for (const group of this.offer()) {
      const entry = byCourse.get(group.course_id) ?? { base: group, groups: [], current: null, pending: false };
      if (group.group_id === null) entry.pending = true;
      else entry.groups.push(group);
      if (group.mine) entry.current = group;
      byCourse.set(group.course_id, entry);
    }
    return [...byCourse.values()].map(({ base, groups, current, pending }) => ({
      courseId: base.course_id,
      code: base.course_code,
      name: base.course_name,
      cycle: base.cycle,
      groups,
      current,
      pending,
    }));
  });

  readonly cycles = computed(() => [...new Set(this.allCourses().map((course) => course.cycle))].sort((a, b) => a - b));

  readonly courses = computed(() => {
    const term = this.query().trim().toLowerCase();
    return this.allCourses().filter(
      (course) =>
        course.cycle === this.cycle() &&
        (!term || course.code.toLowerCase().includes(term) || course.name.toLowerCase().includes(term)),
    );
  });

  readonly enrolledCount = computed(() => this.allCourses().filter((course) => course.current).length);
  readonly selectedIds = computed(() => Object.keys(this.selection()).map(Number));
  readonly selectedCourses = computed(() => this.allCourses().filter((course) => course.courseId in this.selection()));

  readonly chosenGroups = computed(() => {
    const chosen = new Map<number, OfferGroup>();
    for (const course of this.selectedCourses()) {
      const group = this.groupFor(course);
      if (group) chosen.set(course.courseId, group);
    }
    return chosen;
  });

  readonly selectionConflicts = computed(() => {
    const conflicts = new Map<number, string>();
    const entries = [...this.chosenGroups().entries()];
    for (const [courseId, group] of entries) {
      for (const [otherId, other] of entries) {
        if (courseId === otherId || conflicts.has(courseId)) continue;
        if (group.blocks.some((a) => other.blocks.some((b) => overlap(a, b)))) {
          conflicts.set(courseId, other.course_code);
        }
      }
    }
    return conflicts;
  });

  readonly missingChoices = computed(() =>
    this.selectedCourses().filter((course) => course.groups.length > 1 && this.selection()[course.courseId] === null),
  );

  readonly canConfirm = computed(
    () =>
      this.open() &&
      this.selectedIds().length > 0 &&
      this.missingChoices().length === 0 &&
      this.selectionConflicts().size === 0 &&
      !this.confirming(),
  );

  constructor() {
    void this.load(true);
  }

  async load(first = false): Promise<void> {
    if (first) this.loading.set(true);
    try {
      const [status, offer] = await Promise.all([firstValueFrom(this.api.myStatus()), firstValueFrom(this.api.myOffer())]);
      this.status.set(status);
      this.offer.set(offer);
      this.error.set(null);
      if (first) this.cycle.set(this.initialCycle(status, offer));
    } catch (err) {
      this.error.set(extractDetail(err));
    } finally {
      this.loading.set(false);
    }
  }

  setCycle(cycle: number): void {
    this.cycle.set(cycle);
  }

  selectedInCycle(cycle: number): number {
    return this.selectedCourses().filter((course) => course.cycle === cycle).length;
  }

  isSelected(course: CourseOffer): boolean {
    return course.courseId in this.selection();
  }

  blockedReason(course: CourseOffer): string | null {
    if (course.current) return null;
    if (course.pending || course.groups.length === 0) return null;
    const free = course.groups.filter((group) => !group.full && !group.conflict);
    if (free.length > 0) return null;
    if (course.groups.every((group) => group.full)) return 'Cupo lleno';
    return `Se cruza con ${course.groups.find((group) => group.conflict)?.conflict}`;
  }

  toggle(course: CourseOffer): void {
    if (!this.open() || course.current || this.blockedReason(course)) return;
    this.selection.update((current) => {
      const next = { ...current };
      if (course.courseId in next) delete next[course.courseId];
      else next[course.courseId] = this.defaultGroup(course);
      return next;
    });
    this.outcome.set(null);
  }

  chooseGroup(course: CourseOffer, groupId: number): void {
    this.selection.update((current) => ({ ...current, [course.courseId]: groupId }));
  }

  clearSelection(): void {
    this.selection.set({});
    this.outcome.set(null);
  }

  groupSelectable(group: OfferGroup): boolean {
    return !group.full && !group.conflict;
  }

  async confirm(): Promise<void> {
    if (!this.canConfirm()) return;
    this.confirming.set(true);
    try {
      const items = this.selectedCourses().map((course) => ({
        course_id: course.courseId,
        group_id: this.groupFor(course)?.group_id ?? null,
      }));
      const outcome = await firstValueFrom(this.api.enrollSelection(items));
      this.outcome.set(outcome);
      const failed = new Set(outcome.results.filter((row) => row.status === 'failed').map((row) => row.course_id));
      this.selection.update((current) =>
        Object.fromEntries(Object.entries(current).filter(([courseId]) => failed.has(Number(courseId)))),
      );
      this.toast.add({
        severity: outcome.failed > 0 ? 'warn' : 'success',
        summary: 'Matrícula procesada',
        detail: `${outcome.ok} curso(s) matriculados${outcome.skipped ? `, ${outcome.skipped} ya los tenías` : ''}${outcome.failed ? `, ${outcome.failed} con problemas` : ''}.`,
        life: 5500,
      });
      await this.load();
    } catch (err) {
      this.toast.add({ severity: 'error', summary: 'No se pudo matricular', detail: extractDetail(err), life: 6000 });
    } finally {
      this.confirming.set(false);
    }
  }

  async switchTo(course: CourseOffer, group: OfferGroup): Promise<void> {
    if (!course.current || group.group_id === null || course.current.group_id === null) return;
    const from = course.current.group_id;
    const to = group.group_id;
    await this.run(to, () => this.api.switchMine(from, to), `Cambiaste al grupo ${group.group_code}`);
  }

  askWithdraw(course: CourseOffer): void {
    this.confirmingWithdraw.set(course.courseId);
  }

  cancelWithdraw(): void {
    this.confirmingWithdraw.set(null);
  }

  async withdraw(course: CourseOffer): Promise<void> {
    const groupId = course.current?.group_id;
    this.confirmingWithdraw.set(null);
    if (groupId === null || groupId === undefined) return;
    await this.run(groupId, () => this.api.withdrawMe(groupId), 'Retiraste el curso');
  }

  failureOf(courseId: number): string | null {
    return this.outcome()?.results.find((row) => row.course_id === courseId && row.status === 'failed')?.reason ?? null;
  }

  private groupFor(course: CourseOffer): OfferGroup | null {
    const choice = this.selection()[course.courseId];
    if (course.groups.length === 1) return course.groups[0];
    if (choice === null || choice === undefined) return null;
    return course.groups.find((group) => group.group_id === choice) ?? null;
  }

  private defaultGroup(course: CourseOffer): Choice {
    if (course.groups.length === 1) return course.groups[0].group_id;
    return null;
  }

  private initialCycle(status: EnrollmentStatus, offer: OfferGroup[]): number {
    const available = [...new Set(offer.map((group) => group.cycle))].sort((a, b) => a - b);
    const wanted = status.student_cycle ?? offer.find((group) => group.mine)?.cycle ?? 1;
    return available.includes(wanted) ? wanted : (available[0] ?? 1);
  }

  private async run(busyId: number, request: () => Observable<unknown>, message: string): Promise<void> {
    this.busy.set(busyId);
    try {
      await firstValueFrom(request());
      this.toast.add({ severity: 'success', summary: message, life: 3000 });
      await this.load();
    } catch (err) {
      this.toast.add({ severity: 'error', summary: 'No se pudo completar', detail: extractDetail(err), life: 6000 });
    } finally {
      this.busy.set(null);
    }
  }
}
