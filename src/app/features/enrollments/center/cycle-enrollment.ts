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
import { SelectModule } from 'primeng/select';
import { firstValueFrom } from 'rxjs';

import { BulkResult, CyclePackage, EnrollmentPair, PackageLetter } from '../../../core/models/enrollment';
import { Person } from '../../../core/models/catalog';
import { CatalogApi } from '../../../core/services/catalog-api';
import { EnrollmentApi } from '../../../core/services/enrollment-api';
import { extractDetail } from '../../../shared/utils/api-error';
import { CYCLES, toRoman } from '../../../shared/utils/cycles';
import { blocksLabel } from '../../../shared/utils/weekdays';
import { UiAlert } from '../../../shared/components/ui-alert/ui-alert';
import { UiButton } from '../../../shared/components/ui-button/ui-button';
import { UiInput } from '../../../shared/components/ui-input/ui-input';

export interface PickedStudent {
  readonly id: number;
  readonly code: string | null;
  readonly full_name: string;
  readonly semester: number | null;
}

type Source = 'search' | 'codes' | 'cycle';

const MAX_STUDENTS = 300;
const PAGE_SIZE = 100;
const CODE_PATTERN = /\d{4,}/g;

const CYCLE_OPTIONS = CYCLES.map((cycle) => ({ label: `Ciclo ${toRoman(cycle)}`, value: cycle }));

@Component({
  selector: 'app-cycle-enrollment',
  imports: [FormsModule, SelectModule, UiAlert, UiButton, UiInput],
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  templateUrl: './cycle-enrollment.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { class: 'block' },
})
export class CycleEnrollment {
  private readonly api = inject(EnrollmentApi);
  private readonly catalog = inject(CatalogApi);
  private readonly toast = inject(MessageService);

  readonly cycleOptions = CYCLE_OPTIONS;
  readonly roman = toRoman;
  readonly blocksLabel = blocksLabel;

  readonly cycle = signal<number | null>(null);
  readonly letters = signal<PackageLetter[]>([]);
  readonly letter = signal<string | null>(null);
  readonly pkg = signal<CyclePackage | null>(null);
  readonly loadingPackage = signal(false);
  readonly packageError = signal<string | null>(null);

  readonly source = signal<Source>('search');
  readonly query = signal('');
  readonly found = signal<Person[]>([]);
  readonly searching = signal(false);
  readonly pasted = signal('');
  readonly unknownCodes = signal<string[]>([]);
  readonly resolving = signal(false);
  readonly cycleSource = signal<number | null>(null);
  readonly loadingCycle = signal(false);
  readonly picked = signal<PickedStudent[]>([]);

  readonly confirming = signal(false);
  readonly result = signal<BulkResult | null>(null);

  private searchTimer: ReturnType<typeof setTimeout> | null = null;

  readonly pickedIds = computed(() => new Set(this.picked().map((student) => student.id)));
  readonly minFree = computed(() => {
    const courses = this.pkg()?.courses ?? [];
    return courses.length ? Math.min(...courses.map((course) => course.free)) : 0;
  });
  readonly tightCourses = computed(() =>
    (this.pkg()?.courses ?? []).filter((course) => course.free < this.picked().length),
  );
  readonly totalPairs = computed(() => this.picked().length * (this.pkg()?.courses.length ?? 0));
  readonly canConfirm = computed(
    () => this.picked().length > 0 && (this.pkg()?.courses.length ?? 0) > 0 && !this.confirming(),
  );

  readonly failures = computed(() => this.groupFailures(this.result()?.results ?? []));

  async onCycle(cycle: number | null): Promise<void> {
    this.cycle.set(cycle);
    this.letter.set(null);
    this.pkg.set(null);
    this.letters.set([]);
    this.result.set(null);
    this.packageError.set(null);
    if (cycle === null) return;
    try {
      const letters = await firstValueFrom(this.api.letters(cycle));
      this.letters.set(letters);
      if (letters.length === 0) {
        this.packageError.set('No hay grupos activos para ese ciclo en el periodo vigente.');
        return;
      }
      const best = [...letters].sort((a, b) => b.courses_covered - a.courses_covered)[0];
      await this.onLetter(best.group_code);
    } catch (err) {
      this.packageError.set(extractDetail(err));
    }
  }

  async onLetter(letter: string): Promise<void> {
    const cycle = this.cycle();
    if (cycle === null) return;
    this.letter.set(letter);
    this.result.set(null);
    this.loadingPackage.set(true);
    this.packageError.set(null);
    try {
      this.pkg.set(await firstValueFrom(this.api.packagePreview(cycle, letter)));
    } catch (err) {
      this.pkg.set(null);
      this.packageError.set(extractDetail(err));
    } finally {
      this.loadingPackage.set(false);
    }
  }

  setSource(source: Source): void {
    this.source.set(source);
  }

  onQuery(value: string): void {
    this.query.set(value);
    if (this.searchTimer) clearTimeout(this.searchTimer);
    this.searchTimer = setTimeout(() => void this.search(), 250);
  }

  private async search(): Promise<void> {
    const term = this.query().trim();
    if (term.length < 2) {
      this.found.set([]);
      return;
    }
    this.searching.set(true);
    try {
      const page = await firstValueFrom(this.catalog.students({ q: term, page_size: 20 }));
      this.found.set(page.items);
    } catch (err) {
      this.toast.add({ severity: 'error', summary: 'No se pudo buscar', detail: extractDetail(err), life: 4000 });
    } finally {
      this.searching.set(false);
    }
  }

  add(students: PickedStudent[]): void {
    this.picked.update((current) => {
      const ids = new Set(current.map((student) => student.id));
      const merged = [...current, ...students.filter((student) => !ids.has(student.id))];
      return merged.slice(0, MAX_STUDENTS);
    });
    this.result.set(null);
  }

  addPerson(person: Person): void {
    this.add([{ id: person.id, code: person.code, full_name: person.full_name, semester: person.semester }]);
  }

  addAllFound(): void {
    this.add(this.found().map((p) => ({ id: p.id, code: p.code, full_name: p.full_name, semester: p.semester })));
  }

  remove(id: number): void {
    this.picked.update((current) => current.filter((student) => student.id !== id));
  }

  clearPicked(): void {
    this.picked.set([]);
  }

  async resolveCodes(): Promise<void> {
    const codes = [...new Set(this.pasted().match(CODE_PATTERN) ?? [])];
    if (codes.length === 0) {
      this.toast.add({ severity: 'warn', summary: 'Pega al menos un código', life: 3000 });
      return;
    }
    this.resolving.set(true);
    try {
      const result = await firstValueFrom(this.api.resolveStudents(codes));
      this.add(result.found);
      this.unknownCodes.set(result.unknown);
      this.pasted.set('');
      this.toast.add({
        severity: result.unknown.length ? 'warn' : 'success',
        summary: `${result.found.length} alumno(s) agregado(s)`,
        detail: result.unknown.length ? `${result.unknown.length} código(s) no se encontraron.` : undefined,
        life: 4000,
      });
    } catch (err) {
      this.toast.add({ severity: 'error', summary: 'No se pudieron leer los códigos', detail: extractDetail(err), life: 5000 });
    } finally {
      this.resolving.set(false);
    }
  }

  async addWholeCycle(): Promise<void> {
    const cycle = this.cycleSource();
    if (cycle === null) return;
    this.loadingCycle.set(true);
    try {
      const collected: PickedStudent[] = [];
      for (let page = 1; collected.length < MAX_STUDENTS; page += 1) {
        const result = await firstValueFrom(this.catalog.students({ semester: cycle, page, page_size: PAGE_SIZE }));
        collected.push(
          ...result.items.map((p) => ({ id: p.id, code: p.code, full_name: p.full_name, semester: p.semester })),
        );
        if (collected.length >= result.total || result.items.length === 0) break;
      }
      this.add(collected);
      this.toast.add({
        severity: 'success',
        summary: `${collected.length} alumno(s) del ciclo ${toRoman(cycle)} agregados`,
        life: 3500,
      });
    } catch (err) {
      this.toast.add({ severity: 'error', summary: 'No se pudo cargar el ciclo', detail: extractDetail(err), life: 5000 });
    } finally {
      this.loadingCycle.set(false);
    }
  }

  async confirm(): Promise<void> {
    const cycle = this.cycle();
    const letter = this.letter();
    if (!this.canConfirm() || cycle === null || letter === null) return;
    this.confirming.set(true);
    try {
      const result = await firstValueFrom(
        this.api.enrollPackage({ student_ids: this.picked().map((student) => student.id) }, cycle, letter),
      );
      this.result.set(result);
      this.toast.add({
        severity: result.failed > 0 ? 'warn' : 'success',
        summary: 'Matrícula procesada',
        detail: `${result.ok} matrícula(s) nuevas, ${result.skipped} ya existían, ${result.failed} con problemas.`,
        life: 5500,
      });
      this.pkg.set(await firstValueFrom(this.api.packagePreview(cycle, letter)));
    } catch (err) {
      this.toast.add({ severity: 'error', summary: 'No se pudo matricular', detail: extractDetail(err), life: 7000 });
    } finally {
      this.confirming.set(false);
    }
  }

  startOver(): void {
    this.result.set(null);
    this.picked.set([]);
    this.unknownCodes.set([]);
  }

  private groupFailures(results: EnrollmentPair[]): Array<{ key: string; name: string; reasons: string[] }> {
    const grouped = new Map<number, { key: string; name: string; reasons: string[] }>();
    for (const row of results.filter((item) => item.status === 'failed')) {
      const entry = grouped.get(row.student_id) ?? {
        key: String(row.student_id),
        name: `${row.student_code ?? '—'} · ${row.student_name}`,
        reasons: [],
      };
      entry.reasons.push(`${row.course_code}: ${row.reason ?? 'No se pudo matricular'}`);
      grouped.set(row.student_id, entry);
    }
    return [...grouped.values()];
  }
}
