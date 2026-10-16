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
import { extractDetail } from '../../shared/utils/api-error';
import { AttendanceApi, SessionToday } from '../../core/services/attendance-api';
import { CoursesApi } from '../../core/services/courses-api';
import { AuthService } from '../../core/services/auth/auth';
import { PageHeader } from '../../shared/components/page-header/page-header';
import { UiButton } from '../../shared/components/ui-button/ui-button';
import { UiInput } from '../../shared/components/ui-input/ui-input';
import { UiAlert } from '../../shared/components/ui-alert/ui-alert';
import { DataTable } from '../../shared/components/data-table/data-table';
import { DataTableCellDirective } from '../../shared/components/data-table/data-table-cell.directive';
import { TableColumn } from '../../core/models/table-column';
import {
  AttendanceStatusApi,
  AttendanceToday,
  EnrolledStudent,
  SessionReview,
} from '../../core/models/catalog';

const REFRESH_MS = 60_000; // panel usado en vivo: refresco suave cada minuto

type StatusLabelApi = 'Asistió' | 'Tardanza' | 'Falta' | 'Falta justificada';

const STATUS_LABEL: Record<AttendanceStatusApi, StatusLabelApi> = {
  asistio: 'Asistió',
  tardanza: 'Tardanza',
  falta: 'Falta',
};

const STATUS_SEVERITY: Record<StatusLabelApi, 'success' | 'warn' | 'danger' | 'info'> = {
  'Asistió': 'success',
  'Tardanza': 'warn',
  'Falta': 'danger',
  'Falta justificada': 'info',
};

const ESTADO_OPTIONS: Array<StatusLabelApi | 'Todas'> = [
  'Todas',
  'Asistió',
  'Tardanza',
  'Falta',
  'Falta justificada',
];

/** F3 · Asistencias del día: tabla en vivo, marca manual (RF-21), rectificación
 * (RF-15), justificación puntual (R6) y ciclo de sesiones (cierre RF-26,
 * cancelación R5 y sesiones por revisar R4). */
@Component({
  selector: 'app-attendance',
  imports: [
    FormsModule, PageHeader, UiButton, UiInput, UiAlert, DataTable, DataTableCellDirective,
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
  readonly reviews = signal<SessionReview[]>([]);

  readonly estado = signal<StatusLabelApi | 'Todas'>('Todas');
  readonly estadoOptions = ESTADO_OPTIONS;

  /** Sesión o registro en curso (bloquea los botones de esa fila/tarjeta). */
  readonly busy = signal<string | null>(null);

  // --- Modal RF-21: marca manual sobre la sesión abierta ---
  readonly modalVisible = signal(false);
  readonly modalSession = signal<SessionToday | null>(null);
  readonly matriculados = signal<EnrolledStudent[]>([]);
  readonly matLoading = signal(false);
  readonly marcando = signal<number | null>(null); // student_id en curso
  readonly modalError = signal<string | null>(null);

  // --- Rectificación RF-15 ---
  readonly rectifyTarget = signal<AttendanceToday | null>(null);
  readonly rectifyStatus = signal<AttendanceStatusApi>('asistio');
  readonly rectifyReason = signal('');
  rectifyVisible = false;

  // --- Justificación de UNA falta (R6) ---
  readonly justifyTarget = signal<AttendanceToday | null>(null);
  readonly justifyReason = signal('');
  justifyVisible = false;

  // --- Cierre de sesión (RF-26, admin) ---
  readonly closeTarget = signal<SessionToday | null>(null);
  closeVisible = false;

  // --- Cancelación R5 (sesión abierta) ---
  readonly cancelTarget = signal<SessionToday | null>(null);
  readonly cancelReason = signal('');
  cancelVisible = false;

  // --- Sesiones por revisar R4 ---
  readonly reviewConfirmTarget = signal<SessionReview | null>(null);
  readonly reviewCancelTarget = signal<SessionReview | null>(null);
  readonly reviewReason = signal('');
  reviewConfirmVisible = false;
  reviewCancelVisible = false;

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
    { id: 'actions', header: 'Acciones', align: 'center', width: '6rem' },
  ];

  readonly statusChoices: Array<{ label: StatusLabelApi; value: AttendanceStatusApi }> = [
    { label: 'Asistió', value: 'asistio' },
    { label: 'Tardanza', value: 'tardanza' },
    { label: 'Falta', value: 'falta' },
  ];

  readonly haySesiones = computed(() => this.sesiones().length > 0);
  readonly hayRevisiones = computed(() => this.reviews().length > 0);

  /** Valor del select de estado, derivado de ?status= (asistio/tardanza/falta). */
  readonly estadoSeleccionado = computed<StatusLabelApi | 'Todas'>(() => {
    const raw = this.estadoUrl();
    if (raw === 'asistio' || raw === 'tardanza' || raw === 'falta') return STATUS_LABEL[raw];
    if (raw === 'justificada') return 'Falta justificada';
    return 'Todas';
  });

  readonly filtered = computed(() => {
    void this.estado; // estado interno no persiste; el ?status manda
    const estado = this.estadoSeleccionado();
    const texto = this.query()?.trim().toLowerCase() ?? '';
    return this.records().filter((r) => {
      const label = this.label(r);
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

  get estadoSeverity(): (label: StatusLabelApi) => 'success' | 'warn' | 'danger' | 'info' {
    return (label) => STATUS_SEVERITY[label];
  }

  /** R6: una falta justificada (FJ) no cuenta para el 30 %: se muestra aparte. */
  label(r: AttendanceStatusApi | AttendanceToday): StatusLabelApi {
    if (typeof r === 'string') return STATUS_LABEL[r];
    return r.is_justified && r.status === 'falta' ? 'Falta justificada' : STATUS_LABEL[r.status];
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
    const raw = value === 'Todas' ? null : value === 'Falta justificada' ? 'justificada' : value;
    void this.qp.update({ status: raw });
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

  // ---------------------------------------------------------------------
  // Rectificación (RF-15)
  // ---------------------------------------------------------------------
  openRectify(r: AttendanceToday): void {
    this.rectifyTarget.set(r);
    this.rectifyStatus.set(r.status);
    this.rectifyReason.set('');
    this.rectifyVisible = true;
  }

  async confirmRectify(): Promise<void> {
    const r = this.rectifyTarget();
    if (!r) return;
    const reason = this.rectifyReason().trim();
    if (reason.length < 5) {
      this.toast.add({
        severity: 'warn',
        summary: 'Falta el motivo',
        detail: 'La rectificación necesita un motivo de al menos 5 caracteres',
        life: 3500,
      });
      return;
    }
    this.busy.set(`rectify-${r.record_id}`);
    try {
      await this.api.rectify(r.record_id, { new_status: this.rectifyStatus(), reason }).toPromise();
      this.toast.add({
        severity: 'success',
        summary: 'Asistencia rectificada',
        detail: `${r.student_name}: ${this.label(this.rectifyStatus())}`,
        life: 3500,
      });
      this.rectifyVisible = false;
      this.rectifyTarget.set(null);
      await this.load();
    } catch (err) {
      this.toast.add({
        severity: 'error',
        summary: 'No se pudo rectificar',
        detail: extractDetail(err),
        life: 5500,
      });
    } finally {
      this.busy.set(null);
    }
  }

  // ---------------------------------------------------------------------
  // Justificar UNA falta (R6)
  // ---------------------------------------------------------------------
  openJustify(r: AttendanceToday): void {
    this.justifyTarget.set(r);
    this.justifyReason.set('');
    this.justifyVisible = true;
  }

  async confirmJustify(): Promise<void> {
    const r = this.justifyTarget();
    if (!r) return;
    const reason = this.justifyReason().trim();
    if (reason.length < 5) {
      this.toast.add({
        severity: 'warn',
        summary: 'Falta el motivo',
        detail: 'Indica el motivo de la justificación (5 caracteres como mínimo)',
        life: 3500,
      });
      return;
    }
    this.busy.set(`justify-${r.record_id}`);
    try {
      await this.api.justify(r.record_id, { reason }).toPromise();
      this.toast.add({
        severity: 'success',
        summary: 'Falta justificada (FJ)',
        detail: 'Deja de contar para el 30 % de inasistencias',
        life: 4000,
      });
      this.justifyVisible = false;
      this.justifyTarget.set(null);
      await this.load();
    } catch (err) {
      this.toast.add({
        severity: 'error',
        summary: 'No se pudo justificar',
        detail: extractDetail(err),
        life: 5500,
      });
    } finally {
      this.busy.set(null);
    }
  }

  // ---------------------------------------------------------------------
  // Cierre de la sesión (RF-26, admin)
  // ---------------------------------------------------------------------
  askClose(s: SessionToday): void {
    this.closeTarget.set(s);
    this.closeVisible = true;
  }

  async confirmClose(): Promise<void> {
    const s = this.closeTarget();
    if (!s) return;
    this.busy.set(`close-${s.session_id}`);
    try {
      const res = await this.api.closeSession(s.session_id).toPromise();
      this.toast.add({
        severity: 'success',
        summary: 'Sesión cerrada',
        detail: `Faltas generadas: ${res?.faltas ?? 0} · alertas DPI: ${res?.alertas ?? 0}`,
        life: 5000,
      });
      this.closeVisible = false;
      this.closeTarget.set(null);
      await this.load();
    } catch (err) {
      this.toast.add({
        severity: 'error',
        summary: 'No se pudo cerrar la sesión',
        detail: extractDetail(err),
        life: 5500,
      });
    } finally {
      this.busy.set(null);
    }
  }

  // ---------------------------------------------------------------------
  // Cancelación R5 (sesión abierta: día sin clase, paro, falla del docente)
  // ---------------------------------------------------------------------
  askCancel(s: SessionToday): void {
    this.cancelTarget.set(s);
    this.cancelReason.set('');
    this.cancelVisible = true;
  }

  async confirmCancel(): Promise<void> {
    const s = this.cancelTarget();
    if (!s) return;
    const reason = this.cancelReason().trim();
    if (reason.length < 5) {
      this.toast.add({
        severity: 'warn',
        summary: 'Falta el motivo',
        detail: 'Cancelar una sesión necesita un motivo (5 caracteres como mínimo)',
        life: 3500,
      });
      return;
    }
    this.busy.set(`cancel-${s.session_id}`);
    try {
      await this.api.cancelSession(s.session_id, { reason }).toPromise();
      this.toast.add({
        severity: 'success',
        summary: 'Sesión cancelada',
        detail: 'No se generan faltas; la sesión queda fuera de las consultas y del DPI',
        life: 4500,
      });
      this.cancelVisible = false;
      this.cancelTarget.set(null);
      await this.load();
    } catch (err) {
      this.toast.add({
        severity: 'error',
        summary: 'No se pudo cancelar la sesión',
        detail: extractDetail(err),
        life: 5500,
      });
    } finally {
      this.busy.set(null);
    }
  }

  // ---------------------------------------------------------------------
  // Sesiones por revisar (R4): cerradas sin ninguna marca
  // ---------------------------------------------------------------------
  askReviewConfirm(s: SessionReview): void {
    this.reviewConfirmTarget.set(s);
    this.reviewConfirmVisible = true;
  }

  async confirmReviewFaltas(): Promise<void> {
    const s = this.reviewConfirmTarget();
    if (!s) return;
    this.busy.set(`review-${s.session_id}`);
    try {
      const res = await this.api
        .resolveReview(s.session_id, { action: 'confirmar_faltas' })
        .toPromise();
      this.toast.add({
        severity: 'success',
        summary: 'Faltas confirmadas',
        detail: `${s.course_code} G${s.group_code} · ${res?.faltas ?? 0} falta(s) generada(s)`,
        life: 4500,
      });
      this.reviewConfirmVisible = false;
      this.reviewConfirmTarget.set(null);
      await this.load();
    } catch (err) {
      this.toast.add({
        severity: 'error',
        summary: 'No se pudo resolver la sesión',
        detail: extractDetail(err),
        life: 5500,
      });
    } finally {
      this.busy.set(null);
    }
  }

  askReviewCancel(s: SessionReview): void {
    this.reviewCancelTarget.set(s);
    this.reviewReason.set('');
    this.reviewCancelVisible = true;
  }

  async confirmReviewCancel(): Promise<void> {
    const s = this.reviewCancelTarget();
    if (!s) return;
    const reason = this.reviewReason().trim();
    if (reason.length < 5) {
      this.toast.add({
        severity: 'warn',
        summary: 'Falta el motivo',
        detail: 'Cancelar la sesión necesita un motivo (5 caracteres como mínimo)',
        life: 3500,
      });
      return;
    }
    this.busy.set(`review-${s.session_id}`);
    try {
      await this.api.resolveReview(s.session_id, { action: 'cancelar', reason }).toPromise();
      this.toast.add({
        severity: 'success',
        summary: 'Sesión cancelada',
        detail: 'Se registró el motivo en la bitácora',
        life: 4000,
      });
      this.reviewCancelVisible = false;
      this.reviewCancelTarget.set(null);
      await this.load();
    } catch (err) {
      this.toast.add({
        severity: 'error',
        summary: 'No se pudo cancelar la sesión',
        detail: extractDetail(err),
        life: 5500,
      });
    } finally {
      this.busy.set(null);
    }
  }

  shortDate(iso: string): string {
    return iso || '—';
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
      const [sesiones, revisiones] = await Promise.all([
        this.api.sessionsToday().toPromise(),
        this.api.sessionsReview().toPromise(),
      ]);
      this.sesiones.set(sesiones ?? []);
      this.reviews.set(revisiones ?? []);
    } catch (err) {
      this.error.set(extractDetail(err));
    } finally {
      this.loading.set(false);
    }
  }
}
