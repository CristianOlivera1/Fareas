import {
  ChangeDetectionStrategy,
  Component,
  CUSTOM_ELEMENTS_SCHEMA,
  DestroyRef,
  computed,
  effect,
  inject,
  signal,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { MessageService } from 'primeng/api';
import { DialogModule } from 'primeng/dialog';
import { SelectModule } from 'primeng/select';
import { TagModule } from 'primeng/tag';
import { interval } from 'rxjs';

import { QueryParams } from '../../shared/utils/query-params';
import { AttendanceApi, SessionToday } from '../../core/services/attendance-api';
import { CoursesApi } from '../../core/services/courses-api';
import { AuthService } from '../../core/services/auth/auth';
import { PageHeader } from '../../shared/components/page-header/page-header';
import { UiButton } from '../../shared/components/ui-button/ui-button';
import { UiAlert } from '../../shared/components/ui-alert/ui-alert';
import { DataTable } from '../../shared/components/data-table/data-table';
import { DataTableCellDirective } from '../../shared/components/data-table/data-table-cell.directive';
import { TableColumn } from '../../core/models/table-column';
import {
  AttendanceStatusApi,
  AttendanceToday,
  EnrolledStudent,
} from '../../core/models/catalog';
import { extractDetail } from '../catalog/rooms/rooms';

const REFRESH_MS = 60_000; // panel usado en vivo: refresco suave cada minuto

type StatusLabelApi = 'Asistió' | 'Tardanza' | 'Falta';

const STATUS_LABEL: Record<AttendanceStatusApi, StatusLabelApi> = {
  asistio: 'Asistió',
  tardanza: 'Tardanza',
  falta: 'Falta',
};

const STATUS_SEVERITY: Record<StatusLabelApi, 'success' | 'warn' | 'danger'> = {
  'Asistió': 'success',
  'Tardanza': 'warn',
  'Falta': 'danger',
};

@Component({
  selector: 'app-attendance',
  imports: [
    FormsModule, PageHeader, UiButton, UiAlert, DataTable, DataTableCellDirective,
    DialogModule, SelectModule, TagModule,
  ],
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  templateUrl: './attendance.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class Attendance {
  protected readonly auth = inject(AuthService);
  private readonly api = inject(AttendanceApi);
  private readonly courses = inject(CoursesApi);
  private readonly qp = inject(QueryParams);
  private readonly toast = inject(MessageService);
  private readonly destroyRef = inject(DestroyRef);

  readonly query = this.qp.filter('q');
  readonly estadoUrl = this.qp.filter('status');

  readonly records = signal<AttendanceToday[]>([]);
  readonly loading = signal(false);
  readonly error = signal<string | null>(null);
  readonly lastRefresh = signal('—');

  readonly sesiones = signal<SessionToday[]>([]);

  readonly estado = signal<StatusLabelApi | 'Todas'>('Todas');
  readonly estadoOptions: (StatusLabelApi | 'Todas')[] = ['Todas', 'Asistió', 'Tardanza', 'Falta'];

  // --- Modal RF-21: marca manual sobre la sesión abierta ---
  readonly modalVisible = signal(false);
  readonly modalSession = signal<SessionToday | null>(null);
  readonly matriculados = signal<EnrolledStudent[]>([]);
  readonly matLoading = signal(false);
  readonly marcando = signal<number | null>(null); // student_id en curso
  readonly modalError = signal<string | null>(null);

  readonly columns: TableColumn[] = [
    { id: 'index', header: 'N°', align: 'center', width: '3.5rem' },
    { id: 'student_name', header: 'Estudiante' },
    { id: 'course_code', header: 'Curso' },
    { id: 'course_name', header: 'Nombre del curso', hiddenOnMobile: true },
    { id: 'group_code', header: 'Grupo', align: 'center' },
    { id: 'room_code', header: 'Aula', hiddenOnMobile: true },
    { id: 'marked_at', header: 'Ingreso' },
    { id: 'method', header: 'Método', hiddenOnMobile: true },
    { id: 'status', header: 'Estado', align: 'right' },
  ];

  readonly haySesiones = computed(() => this.sesiones().length > 0);

  /** Valor del select de estado, derivado de ?status= (asistio/tardanza/falta). */
  readonly estadoSeleccionado = computed<StatusLabelApi | 'Todas'>(() => {
    const raw = this.estadoUrl();
    if (raw === 'asistio' || raw === 'tardanza' || raw === 'falta') return STATUS_LABEL[raw];
    return 'Todas';
  });

  readonly filtered = computed(() => {
    void this.estado; // estado interno no persiste; el ?status manda
    const estado = this.estadoSeleccionado();
    const texto = this.query()?.trim().toLowerCase() ?? '';
    return this.records().filter((r) => {
      const label = STATUS_LABEL[r.status];
      const okTexto =
        !texto ||
        r.student_name.toLowerCase().includes(texto) ||
        r.student_code?.toLowerCase().includes(texto) ||
        r.course_code.toLowerCase().includes(texto) ||
        r.course_name.toLowerCase().includes(texto);
      const okEstado = estado === 'Todas' || label === estado;
      return okTexto && okEstado;
    });
  });

  trackById(_index: number, row: unknown): number {
    return (row as AttendanceToday).record_id;
  }

  constructor() {
    // Recarga cuando cambian los query params (search o estado)
    effect(() => {
      this.query(); this.estadoUrl();
      void this.load();
    });

    // Auto-refresh suave del panel (usa el enlace de la app). RF-26: hay
    // actividades en vivo que cambian sin navegador abierto.
    interval(REFRESH_MS)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => void this.load());
  }

  get estadoSeverity(): (label: StatusLabelApi) => 'success' | 'warn' | 'danger' {
    return (label) => STATUS_SEVERITY[label];
  }

  label(s: AttendanceStatusApi): StatusLabelApi {
    return STATUS_LABEL[s];
  }

  shortHour(iso: string | null): string {
    return iso && iso.length >= 16 ? iso.slice(11, 16) : '—';
  }

  clearFilters(): void {
    void this.qp.update({ q: null, status: null });
  }

  onSearch(value: string): void {
    void this.qp.update({ q: value || null });
  }

  onEstado(value: StatusLabelApi | 'Todas'): void {
    void this.qp.update({ status: value === 'Todas' ? null : value });
  }

  reload(): void {
    void this.load();
  }

  // ---------------------------------------------------------------------
  // Modal RF-21 (marca manual)
  // ---------------------------------------------------------------------
  openModal(s: SessionToday): void {
    this.modalSession.set(s);
    this.modalVisible.set(true);
    this.modalError.set(null);
    void this.loadEnrolled(s.group_id);
  }

  closeModal(): void {
    this.modalVisible.set(false);
    this.modalSession.set(null);
    this.matriculados.set([]);
    this.modalError.set(null);
  }

  async marcaManual(studentId: number, status: AttendanceStatusApi): Promise<void> {
    const ses = this.modalSession();
    if (!ses) return;
    this.marcando.set(studentId);
    this.modalError.set(null);
    try {
      await this.api.manualMark(ses.session_id, { student_id: studentId, status }).toPromise();
      this.toast.add({ severity: 'success', summary: 'Asistencia registrada', life: 2200 });
      await this.load(); // refresca los registros de hoy (la marca entra con method=manual)
    } catch (err) {
      this.modalError.set(extractDetail(err));
    } finally {
      this.marcando.set(null);
    }
  }

  private async loadEnrolled(groupId: number): Promise<void> {
    this.matLoading.set(true);
    try {
      const list = await this.courses.enrolled(groupId).toPromise();
      this.matriculados.set(list ?? []);
    } catch (err) {
      this.modalError.set(extractDetail(err));
    } finally {
      this.matLoading.set(false);
    }
  }

  private async load(): Promise<void> {
    this.loading.set(true);
    this.error.set(null);
    try {
      const hoy = await this.api.today({ page_size: 500 }).toPromise();
      this.records.set(hoy ?? []);
      this.lastRefresh.set(
        new Date().toLocaleTimeString('es-PE', { hour: '2-digit', minute: '2-digit' }),
      );
      this.sesiones.set((await this.api.sessionsToday().toPromise()) ?? []);
    } catch (err) {
      this.error.set(extractDetail(err));
    } finally {
      this.loading.set(false);
    }
  }
}
