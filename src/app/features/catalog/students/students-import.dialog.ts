import {
  ChangeDetectionStrategy,
  Component,
  CUSTOM_ELEMENTS_SCHEMA,
  computed,
  inject,
  model,
  output,
  signal,
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MessageService } from 'primeng/api';
import { DialogModule } from 'primeng/dialog';
import { SelectModule } from 'primeng/select';

import { UiAlert } from '../../../shared/components/ui-alert/ui-alert';
import { UiButton } from '../../../shared/components/ui-button/ui-button';
import { FileDrop } from '../../../shared/components/file-drop/file-drop';
import { CatalogApi } from '../../../core/services/catalog-api';
import { CoursesApi } from '../../../core/services/courses-api';
import { CalendarApi } from '../../../core/services/calendar-api';
import { extractDetail } from '../../../shared/utils/api-error';
import {
  StudentImportEditableRow,
  StudentImportPreview,
  StudentImportResult,
} from '../../../core/models/imports';

interface Option<T> {
  readonly label: string;
  readonly value: T;
}

const STEPS = [
  { number: 1, label: 'Archivo' },
  { number: 2, label: 'Revisar nómina' },
  { number: 3, label: 'Resultado' },
];

const CYCLES: Option<number>[] = Array.from({ length: 12 }, (_, index) => ({
  label: `Ciclo ${index + 1}`,
  value: index + 1,
}));

@Component({
  selector: 'app-students-import-dialog',
  imports: [FormsModule, DialogModule, SelectModule, UiButton, UiAlert, FileDrop],
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  templateUrl: './students-import.dialog.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class StudentsImportDialog {
  private readonly api = inject(CatalogApi);
  private readonly courses = inject(CoursesApi);
  private readonly calendar = inject(CalendarApi);
  private readonly toast = inject(MessageService);

  readonly visible = model(false);
  readonly imported = output<void>();

  readonly steps = STEPS;
  readonly cycles = CYCLES;

  readonly step = signal(1);
  readonly file = signal<File | null>(null);
  readonly defaultSemester = signal(1);
  readonly bulkSemester = signal(1);
  readonly preview = signal<StudentImportPreview | null>(null);
  readonly rows = signal<StudentImportEditableRow[]>([]);
  readonly result = signal<StudentImportResult | null>(null);
  readonly loading = signal(false);
  readonly confirming = signal(false);
  readonly error = signal<string | null>(null);
  readonly groupId = signal<number | null>(null);
  readonly groupOptions = signal<Option<number>[]>([]);

  private nextRow = 0;

  readonly canRead = computed(() => this.file() !== null && !this.loading());
  readonly invalidCount = computed(
    () => this.rows().filter((row) => this.rowIssues(row).length > 0).length,
  );
  readonly canConfirm = computed(
    () => this.rows().length > 0 && this.invalidCount() === 0 && !this.confirming(),
  );
  readonly typeLabel = computed(() => this.documentLabel(this.preview()?.tipo));

  constructor() {
    void this.loadGroups();
  }

  private async loadGroups(): Promise<void> {
    try {
      const cfg = await this.calendar.settings().toPromise();
      const semester = cfg?.semester_label;
      const groups = await this.courses
        .groups({ semester: semester ?? undefined, include_inactive: false })
        .toPromise();
      this.groupOptions.set(
        (groups ?? []).map((group) => ({
          label: `${group.course_code} · Grupo ${group.group_code} — ${group.teacher_name ?? 'Sin docente'}`,
          value: group.id,
        })),
      );
    } catch {
      this.groupOptions.set([]);
    }
  }

  onShow(): void {
    this.step.set(1);
    this.file.set(null);
    this.defaultSemester.set(1);
    this.bulkSemester.set(1);
    this.preview.set(null);
    this.rows.set([]);
    this.result.set(null);
    this.error.set(null);
    this.groupId.set(null);
    this.nextRow = 0;
  }

  onHide(): void {
    if (this.result()) this.imported.emit();
  }

  close(): void {
    this.visible.set(false);
  }

  onFile(file: File | null): void {
    this.file.set(file);
    this.preview.set(null);
    this.rows.set([]);
    this.result.set(null);
    this.error.set(null);
  }

  onFileError(message: string): void {
    this.toast.add({ severity: 'error', summary: 'Archivo no válido', detail: message, life: 4500 });
  }

  async readRoster(): Promise<void> {
    const file = this.file();
    if (!file) {
      this.toast.add({
        severity: 'warn',
        summary: 'Falta el archivo',
        detail: 'Sube una nómina en PDF o una foto antes de leerla.',
        life: 3500,
      });
      return;
    }
    this.loading.set(true);
    this.error.set(null);
    try {
      const preview = await this.api.importStudentsPreview(file, this.defaultSemester()).toPromise();
      if (!preview) return;
      this.preview.set(preview);
      this.nextRow = 0;
      this.rows.set(
        preview.alumnos.map((student) => ({
          key: this.newKey(),
          fila: student.fila,
          code: student.code ?? '',
          dni: student.dni ?? '',
          full_name: student.full_name ?? '',
          email: student.email ?? '',
          email_generado: student.email_generado,
          semester: student.semester,
          whatsapp: student.whatsapp ?? '',
          duplicado: student.duplicado,
          errores: [...student.errores],
          nota: student.nota,
          linea: student.linea,
          pagina: student.pagina,
        })),
      );
      this.step.set(2);
      this.toast.add({
        severity: preview.con_error > 0 ? 'warn' : 'success',
        summary: `${preview.total} fila(s) detectada(s)`,
        detail:
          preview.con_error > 0
            ? `${preview.con_error} fila(s) tienen datos por corregir antes de confirmar.`
            : 'Revisa la nómina y confirma para crear las cuentas.',
        life: 4500,
      });
    } catch (err) {
      this.error.set(extractDetail(err));
      this.toast.add({
        severity: 'error',
        summary: 'No se pudo leer la nómina',
        detail: extractDetail(err),
        life: 6500,
      });
    } finally {
      this.loading.set(false);
    }
  }

  updateRow(key: string, patch: Partial<StudentImportEditableRow>): void {
    this.rows.update((rows) =>
      rows.map((row) =>
        row.key === key
          ? { ...row, ...patch, errores: [], duplicado: false, nota: null }
          : row,
      ),
    );
  }

  onCodeInput(key: string, event: Event, field: 'code' | 'dni'): void {
    const value = (event.target as HTMLInputElement).value.replace(/\D/g, '');
    this.updateRow(key, field === 'code' ? { code: value } : { dni: value });
  }

  onTextInput(
    key: string,
    event: Event,
    field: 'full_name' | 'email' | 'whatsapp',
  ): void {
    const value = (event.target as HTMLInputElement).value;
    if (field === 'full_name') {
      this.updateRow(key, { full_name: value });
    } else if (field === 'email') {
      this.updateRow(key, { email: value, email_generado: false });
    } else {
      this.updateRow(key, { whatsapp: value.replace(/\D/g, '') });
    }
  }

  onSemester(key: string, value: number | null): void {
    this.updateRow(key, { semester: value });
  }

  addRow(): void {
    this.rows.update((rows) => [
      ...rows,
      {
        key: this.newKey(),
        fila: rows.length + 1,
        code: '',
        dni: '',
        full_name: '',
        email: '',
        email_generado: false,
        semester: this.defaultSemester(),
        whatsapp: '',
        duplicado: false,
        errores: [],
        nota: 'Fila añadida a mano',
        linea: '',
        pagina: 1,
      },
    ]);
  }

  removeRow(key: string): void {
    this.rows.update((rows) => rows.filter((row) => row.key !== key));
  }

  removeInvalid(): void {
    this.rows.update((rows) => rows.filter((row) => this.rowIssues(row).length === 0));
  }

  applySemesterToAll(): void {
    const semester = this.bulkSemester();
    this.rows.update((rows) =>
      rows.map((row) => ({ ...row, semester, errores: [], duplicado: false, nota: null })),
    );
  }

  rowIssues(row: StudentImportEditableRow): string[] {
    const issues: string[] = [];
    if (!/^\d{6}$/.test(row.code.trim())) issues.push('Código de 6 dígitos');
    if (!/^\d{8}$/.test(row.dni.trim())) issues.push('DNI de 8 dígitos');
    if (row.full_name.trim().length < 3) issues.push('Nombre completo');
    if (!this.validEmail(row.email)) issues.push('Correo válido');
    if (!row.semester || row.semester < 1 || row.semester > 12) issues.push('Ciclo');
    if (row.whatsapp.trim() && !/^9\d{8}$/.test(row.whatsapp.trim())) {
      issues.push('WhatsApp de 9 dígitos que empiece con 9');
    }
    issues.push(...row.errores);
    issues.push(...this.duplicateIssues(row));
    return [...new Set(issues)];
  }

  issuesText(row: StudentImportEditableRow): string {
    return [...new Set([...row.errores, ...this.rowIssues(row)])].join(' · ');
  }

  async confirm(): Promise<void> {
    if (!this.canConfirm()) {
      this.toast.add({
        severity: 'warn',
        summary: 'Hay filas por corregir',
        detail: 'Revisa el código, DNI, nombre, correo y ciclo de cada fila.',
        life: 4200,
      });
      return;
    }
    this.confirming.set(true);
    try {
      const result = await this.api
        .importStudentsConfirm({
          group_id: this.groupId(),
          alumnos: this.rows().map((row) => ({
            fila: row.fila,
            code: row.code.trim(),
            dni: row.dni.trim(),
            full_name: row.full_name.trim(),
            email: row.email.trim().toLowerCase() || null,
            semester: row.semester,
            whatsapp: row.whatsapp.trim() || null,
          })),
        })
        .toPromise();
      if (!result) return;
      this.result.set(result);
      this.step.set(3);
      this.toast.add({
        severity: result.errores.length > 0 ? 'warn' : 'success',
        summary: 'Nómina procesada',
        detail: `${result.creados} cuenta(s) creadas, ${result.omitidos} ya existían.`,
        life: 4500,
      });
    } catch (err) {
      this.toast.add({
        severity: 'error',
        summary: 'No se pudo confirmar la nómina',
        detail: extractDetail(err),
        life: 7000,
      });
    } finally {
      this.confirming.set(false);
    }
  }

  restart(): void {
    if (this.result()) this.imported.emit();
    this.step.set(1);
    this.file.set(null);
    this.preview.set(null);
    this.rows.set([]);
    this.result.set(null);
    this.error.set(null);
    this.groupId.set(null);
  }

  private duplicateIssues(row: StudentImportEditableRow): string[] {
    const issues: string[] = [];
    const rows = this.rows();
    if (row.code && rows.filter((item) => item.code === row.code).length > 1) {
      issues.push('Código repetido en el archivo');
    }
    if (row.dni && rows.filter((item) => item.dni === row.dni).length > 1) {
      issues.push('DNI repetido en el archivo');
    }
    if (row.email && rows.filter((item) => item.email.toLowerCase() === row.email.toLowerCase()).length > 1) {
      issues.push('Correo repetido en el archivo');
    }
    return issues;
  }

  private validEmail(value: string): boolean {
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value.trim());
  }

  private documentLabel(type: string | undefined): string {
    if (type === 'pdf_texto') return 'PDF con texto';
    if (type === 'pdf_ocr') return 'PDF escaneado';
    if (type === 'imagen') return 'Imagen';
    return 'Documento';
  }

  private newKey(): string {
    this.nextRow += 1;
    return `student-${this.nextRow}`;
  }
}
