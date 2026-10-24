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

import { BulkResult, EnrollmentStatus, OfferGroup } from '../../core/models/enrollment';
import { EnrollmentApi } from '../../core/services/enrollment-api';
import { extractDetail } from '../../shared/utils/api-error';
import { toRoman } from '../../shared/utils/cycles';
import { blocksLabel } from '../../shared/utils/weekdays';
import { PageHeader } from '../../shared/components/page-header/page-header';
import { ScheduleEntry, ScheduleTable } from '../../shared/components/schedule-table/schedule-table';
import { UiAlert } from '../../shared/components/ui-alert/ui-alert';
import { UiButton } from '../../shared/components/ui-button/ui-button';
import { UiInput } from '../../shared/components/ui-input/ui-input';

interface CourseOffer {
  readonly courseId: number;
  readonly code: string;
  readonly name: string;
  readonly groups: OfferGroup[];
}

interface LetterCoverage {
  readonly letter: string;
  readonly covered: number;
  readonly total: number;
}

@Component({
  selector: 'app-my-enrollment-page',
  imports: [FormsModule, PageHeader, ScheduleTable, UiAlert, UiButton, UiInput],
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
  readonly quickLetter = signal<string | null>(null);
  readonly quickBusy = signal(false);
  readonly quickResult = signal<BulkResult | null>(null);

  readonly open = computed(() => this.status()?.window.open ?? false);
  readonly mine = computed(() => this.offer().filter((group) => group.mine));

  readonly entries = computed<ScheduleEntry[]>(() =>
    this.mine().flatMap((group) =>
      group.blocks.map((block, index) => ({
        id: `${group.group_id}-${index}`,
        weekday: block.weekday,
        start_time: block.start_time,
        end_time: block.end_time,
        course_code: group.course_code,
        course_name: group.course_name,
        group_code: group.group_code,
        room_code: block.room_code,
        teacher_name: group.teacher_name,
      })),
    ),
  );

  readonly cycles = computed(() => {
    const counts = new Map<number, number>();
    for (const group of this.offer()) counts.set(group.cycle, (counts.get(group.cycle) ?? 0) + 1);
    return [...counts.keys()].sort((a, b) => a - b);
  });

  readonly courses = computed<CourseOffer[]>(() => {
    const term = this.query().trim().toLowerCase();
    const byCourse = new Map<number, CourseOffer>();
    for (const group of this.offer().filter((item) => item.cycle === this.cycle())) {
      const entry = byCourse.get(group.course_id) ?? {
        courseId: group.course_id,
        code: group.course_code,
        name: group.course_name,
        groups: [],
      };
      entry.groups.push(group);
      byCourse.set(group.course_id, entry);
    }
    return [...byCourse.values()].filter(
      (course) => !term || course.code.toLowerCase().includes(term) || course.name.toLowerCase().includes(term),
    );
  });

  readonly letters = computed<LetterCoverage[]>(() => {
    const inCycle = this.offer().filter((group) => group.cycle === this.cycle());
    const total = new Set(inCycle.map((group) => group.course_id)).size;
    const covered = new Map<string, Set<number>>();
    for (const group of inCycle) {
      covered.set(group.group_code, (covered.get(group.group_code) ?? new Set()).add(group.course_id));
    }
    return [...covered.entries()]
      .map(([letter, ids]) => ({ letter, covered: ids.size, total }))
      .sort((a, b) => a.letter.localeCompare(b.letter));
  });

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
      if (first) {
        const wanted = status.student_cycle ?? this.mineCycle(offer) ?? 1;
        const available = [...new Set(offer.map((group) => group.cycle))].sort((a, b) => a - b);
        this.cycle.set(available.includes(wanted) ? wanted : (available[0] ?? 1));
      }
    } catch (err) {
      this.error.set(extractDetail(err));
    } finally {
      this.loading.set(false);
    }
  }

  setCycle(cycle: number): void {
    this.cycle.set(cycle);
    this.quickLetter.set(null);
    this.quickResult.set(null);
  }

  stateOf(group: OfferGroup): 'mine' | 'full' | 'conflict' | 'switch' | 'free' {
    if (group.mine) return 'mine';
    if (group.conflict) return 'conflict';
    if (group.full) return 'full';
    return group.current_group_code ? 'switch' : 'free';
  }

  async enroll(group: OfferGroup): Promise<void> {
    await this.run(group.group_id, () => this.api.enrollMe(group.group_id), 'Te matriculaste');
  }

  async switchTo(group: OfferGroup): Promise<void> {
    const current = this.mine().find((item) => item.course_id === group.course_id);
    if (!current) return;
    await this.run(
      group.group_id,
      () => this.api.switchMine(current.group_id, group.group_id),
      `Cambiaste al grupo ${group.group_code}`,
    );
  }

  askWithdraw(group: OfferGroup): void {
    this.confirmingWithdraw.set(group.group_id);
  }

  cancelWithdraw(): void {
    this.confirmingWithdraw.set(null);
  }

  async withdraw(group: OfferGroup): Promise<void> {
    this.confirmingWithdraw.set(null);
    await this.run(group.group_id, () => this.api.withdrawMe(group.group_id), 'Retiraste el curso');
  }

  async enrollWholeCycle(): Promise<void> {
    const letter = this.quickLetter();
    if (!letter) return;
    this.quickBusy.set(true);
    try {
      const result = await firstValueFrom(this.api.enrollMePackage(this.cycle(), letter));
      this.quickResult.set(result);
      this.toast.add({
        severity: result.failed > 0 ? 'warn' : 'success',
        summary: 'Matrícula del ciclo',
        detail: `${result.ok} curso(s) agregados, ${result.skipped} ya los tenías, ${result.failed} con problemas.`,
        life: 5500,
      });
      await this.load();
    } catch (err) {
      this.toast.add({ severity: 'error', summary: 'No se pudo matricular', detail: extractDetail(err), life: 6000 });
    } finally {
      this.quickBusy.set(false);
    }
  }

  private async run(groupId: number, request: () => Observable<unknown>, message: string): Promise<void> {
    this.busy.set(groupId);
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

  private mineCycle(offer: OfferGroup[]): number | null {
    return offer.find((group) => group.mine)?.cycle ?? null;
  }
}
