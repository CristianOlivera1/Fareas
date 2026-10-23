import {
  ChangeDetectionStrategy,
  Component,
  CUSTOM_ELEMENTS_SCHEMA,
  computed,
  effect,
  inject,
  signal,
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import { SelectModule } from 'primeng/select';

import { Course } from '../../core/models/catalog';
import { TableColumn } from '../../core/models/table-column';
import { AtRiskStudent, DpiApi, DpiLevel } from '../../core/services/dpi-api';
import { CoursesApi } from '../../core/services/courses-api';
import { extractDetail } from '../../shared/utils/api-error';
import { PageHeader } from '../../shared/components/page-header/page-header';
import { UiAlert } from '../../shared/components/ui-alert/ui-alert';
import { UiButton } from '../../shared/components/ui-button/ui-button';
import { DataTable } from '../../shared/components/data-table/data-table';
import { DataTableCellDirective } from '../../shared/components/data-table/data-table-cell.directive';

const LEVELS: ReadonlyArray<{ value: DpiLevel; label: string; hint: string }> = [
  { value: 'alerta', label: 'En riesgo', hint: 'Cerca del límite de inasistencias' },
  { value: 'limite', label: 'Límite superado', hint: 'Superaron el límite: inhabilitados' },
];

@Component({
  selector: 'app-at-risk-page',
  imports: [
    FormsModule,
    SelectModule,
    PageHeader,
    UiAlert,
    UiButton,
    DataTable,
    DataTableCellDirective,
  ],
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  templateUrl: './at-risk.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { class: 'block' },
})
export class AtRiskPage {
  private readonly dpi = inject(DpiApi);
  private readonly coursesApi = inject(CoursesApi);

  readonly levels = LEVELS;
  readonly columns: TableColumn[] = [
    { id: 'student', header: 'Estudiante' },
    { id: 'course_code', header: 'Curso' },
    { id: 'absence_percent', header: 'Faltas', align: 'center' },
    { id: 'lates', header: 'Tardanzas', align: 'center', hiddenOnMobile: true },
    { id: 'justified_absences', header: 'Justificadas', align: 'center', hiddenOnMobile: true },
  ];

  readonly level = signal<DpiLevel>('alerta');
  readonly courseId = signal<number | null>(null);
  readonly courses = signal<Course[]>([]);
  readonly rows = signal<AtRiskStudent[]>([]);
  readonly loading = signal(true);
  readonly error = signal<string | null>(null);

  readonly courseOptions = computed(() => [
    { label: 'Todos mis cursos', value: null },
    ...this.courses().map((course) => ({ label: `${course.code} · ${course.name}`, value: course.id })),
  ]);

  readonly hint = computed(() => LEVELS.find((item) => item.value === this.level())?.hint ?? '');

  constructor() {
    this.coursesApi.courses({ page_size: 100 }).subscribe({
      next: (page) => this.courses.set(page.items),
      error: () => undefined,
    });
    effect(() => this.load(this.level(), this.courseId()));
  }

  reload(): void {
    this.load(this.level(), this.courseId());
  }

  trackRow(_: number, row: unknown): unknown {
    const item = row as AtRiskStudent;
    return `${item.student_id}-${item.course_id}`;
  }

  private load(level: DpiLevel, courseId: number | null): void {
    this.loading.set(true);
    this.error.set(null);
    this.dpi.atRisk(level, courseId).subscribe({
      next: (rows) => {
        this.rows.set(rows);
        this.loading.set(false);
      },
      error: (err) => {
        this.error.set(extractDetail(err));
        this.loading.set(false);
      },
    });
  }
}
