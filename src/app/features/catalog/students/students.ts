import {
  ChangeDetectionStrategy,
  Component,
  CUSTOM_ELEMENTS_SCHEMA,
  computed,
  DestroyRef,
  effect,
  inject,
  signal,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import {
  FormBuilder,
  FormsModule,
  ReactiveFormsModule,
  Validators,
} from '@angular/forms';
import { Person } from '../../../core/models/catalog';
import { TableColumn } from '../../../core/models/table-column';
import { AuthService } from '../../../core/services/auth/auth';
import { CatalogApi } from '../../../core/services/catalog-api';
import { MessageService } from 'primeng/api';
import { DialogModule } from 'primeng/dialog';
import { InputTextModule } from 'primeng/inputtext';
import { SelectModule } from 'primeng/select';
import { ToggleSwitchModule } from 'primeng/toggleswitch';
import { DataTable } from '../../../shared/components/data-table/data-table';
import { DataTableCellDirective } from '../../../shared/components/data-table/data-table-cell.directive';
import { PageHeader } from '../../../shared/components/page-header/page-header';
import { UiAlert } from '../../../shared/components/ui-alert/ui-alert';
import { UiButton } from '../../../shared/components/ui-button/ui-button';
import { UiInput } from '../../../shared/components/ui-input/ui-input';
import { extractDetail } from '../../../shared/utils/api-error';
import { QueryParams } from '../../../shared/utils/query-params';
import {
  DNI_PATTERN,
  INSTITUTIONAL_EMAIL_DOMAIN,
  institutionalEmail,
  nonBlank,
  normalizeWhatsapp,
  peruWhatsapp,
} from '../../../shared/validators/person.validators';
import { StudentsImportDialog } from './students-import.dialog';

const CODE_PATTERN = /^\d{6}$/;
const CICLOS = Array.from({ length: 12 }, (_, i) => ({ label: `${i + 1}`, value: i + 1 }));

@Component({
  selector: 'app-students-page',
  imports: [
    FormsModule, ReactiveFormsModule, PageHeader, UiButton, UiInput, UiAlert, DataTable,
    DataTableCellDirective, DialogModule, InputTextModule, SelectModule, ToggleSwitchModule,
    StudentsImportDialog,
  ],
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  templateUrl: './students.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class StudentsPage {
  protected readonly auth = inject(AuthService);
  private readonly api = inject(CatalogApi);
  private readonly qp = inject(QueryParams);
  private readonly toast = inject(MessageService);
  private readonly fb = inject(FormBuilder);
  private readonly destroyRef = inject(DestroyRef);

  readonly ciclos = CICLOS;
  readonly studentId = signal<number | null>(null);
  readonly isEditing = computed(() => this.studentId() !== null);
  readonly studentForm = this.fb.group({
    full_name: ['', [
      Validators.required,
      nonBlank,
      Validators.minLength(3),
      Validators.maxLength(160),
    ]],
    email: ['', [
      Validators.required,
      Validators.email,
      institutionalEmail,
      Validators.maxLength(160),
    ]],
    dni: ['', [Validators.required, Validators.pattern(DNI_PATTERN)]],
    code: ['', [Validators.required, Validators.pattern(CODE_PATTERN)]],
    semester: [null as number | null, [
      Validators.required,
      Validators.min(1),
      Validators.max(12),
    ]],
    whatsapp: ['', [peruWhatsapp, Validators.maxLength(20)]],
    is_active: [true],
  });

  readonly columns: TableColumn[] = [
    { id: 'index', header: 'N°', width: '60px', align: 'center' },
    { id: 'student', header: 'Estudiante' },
    { id: 'enrolled', header: 'Rostro', align: 'center' },
    { id: 'email', header: 'Correo', hiddenOnMobile: true },
    { id: 'semester', header: 'Ciclo', align: 'center' },
    { id: 'is_active', header: 'Estado', align: 'center', hiddenOnMobile: true },
    { id: 'actions', header: '', align: 'center', width: '70px' },
  ];

  readonly q = this.qp.filter('q');
  readonly semester = this.qp.filter('semester');
  readonly semesterNumber = computed(() => {
    const value = Number(this.semester());
    return Number.isInteger(value) && value >= 1 && value <= 12 ? value : null;
  });
  readonly page = this.qp.number('page', 1);
  readonly pageSize = this.qp.number('page_size', 10);

  readonly students = signal<Person[]>([]);
  readonly total = signal(0);
  readonly loading = signal(false);
  readonly error = signal<string | null>(null);
  readonly saving = signal(false);

  dialogVisible = false;
  importVisible = false;

  constructor() {
    effect(() => {
      this.q(); this.semester(); this.page(); this.pageSize();
      void this.load();
    });

    this.studentForm.controls.dni.valueChanges
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((value) => {
        const digits = (value ?? '').replace(/\D/g, '').slice(0, 8);
        if (digits !== value) {
          this.studentForm.controls.dni.setValue(digits);
        }
      });

    this.studentForm.controls.code.valueChanges
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((value) => {
        const digits = (value ?? '').replace(/\D/g, '').slice(0, 6);
        if (digits !== value) {
          this.studentForm.controls.code.setValue(digits);
        }
      });
  }

  initials(name: string): string {
    const parts = name.trim().split(/\s+/);
    return parts.length >= 2
      ? `${parts[0][0]}${parts[1][0]}`.toUpperCase()
      : name.slice(0, 2).toUpperCase();
  }

  onSearch(value: string): void { void this.qp.update({ q: value || null, page: null }); }
  onSemester(value: number | null): void {
    void this.qp.update({ semester: value ? String(value) : null, page: null });
  }
  onPage(p: number): void { void this.qp.update({ page: p }); }
  onPageSize(s: number): void { void this.qp.update({ page_size: s, page: null }); }
  reload(): void { void this.load(); }

  fieldError(field: 'full_name' | 'email' | 'dni' | 'code' | 'whatsapp'): string {
    const control = this.studentForm.get(field);
    if (!control || !control.touched || !control.errors) return '';
    if (control.errors['required'] || control.errors['blank']) return 'Este campo es obligatorio.';
    if (control.errors['minlength']) {
      return `Mínimo ${control.errors['minlength'].requiredLength} caracteres.`;
    }
    if (control.errors['maxlength']) {
      return `Máximo ${control.errors['maxlength'].requiredLength} caracteres.`;
    }
    if (control.errors['email']) return 'Ingresa un correo válido.';
    if (control.errors['institutional']) {
      return `Usa tu correo institucional (@${INSTITUTIONAL_EMAIL_DOMAIN}).`;
    }
    if (control.errors['pattern']) {
      if (field === 'dni') return 'El DNI debe tener exactamente 8 dígitos.';
      if (field === 'code') return 'El código de matrícula debe tener exactamente 6 dígitos.';
    }
    if (control.errors['whatsapp']) {
      return 'Ingresa un celular peruano de 9 dígitos que empiece con 9.';
    }
    return 'Valor inválido.';
  }

  semesterError(): string {
    const control = this.studentForm.controls.semester;
    if (!control.touched || !control.errors) return '';
    if (control.errors['required']) return 'Selecciona el ciclo.';
    return 'Selecciona un ciclo entre 1 y 12.';
  }

  openCreate(): void {
    this.studentId.set(null);
    this.studentForm.enable();
    this.studentForm.reset({
      full_name: '',
      email: '',
      dni: '',
      code: '',
      semester: null,
      whatsapp: '',
      is_active: true,
    });
    this.dialogVisible = true;
  }

  openImport(): void {
    this.importVisible = true;
  }

  openEdit(s: Person): void {
    this.studentId.set(s.id);
    this.studentForm.reset({
      full_name: s.full_name,
      email: s.email,
      dni: s.dni ?? '',
      code: s.code ?? '',
      semester: s.semester,
      whatsapp: s.whatsapp ?? '',
      is_active: s.is_active,
    });
    this.studentForm.controls.email.disable();
    this.studentForm.controls.dni.disable();
    this.studentForm.controls.code.disable();
    this.studentForm.controls.semester.disable();
    this.dialogVisible = true;
  }

  async save(): Promise<void> {
    if (this.saving()) return;

    if (this.studentForm.invalid) {
      this.studentForm.markAllAsTouched();
      this.toast.add({
        severity: 'warn',
        summary: 'Revisa el formulario',
        detail: 'Corrige los campos marcados antes de guardar.',
        life: 3500,
      });
      return;
    }

    const raw = this.studentForm.getRawValue();
    const fullName = (raw.full_name ?? '').trim();
    const whatsappValue = (raw.whatsapp ?? '').trim();
    const whatsapp = whatsappValue ? normalizeWhatsapp(whatsappValue) : null;
    const studentId = this.studentId();

    this.saving.set(true);
    try {
      if (studentId === null) {
        await this.api.createStudent({
          full_name: fullName,
          email: (raw.email ?? '').trim().toLowerCase(),
          dni: (raw.dni ?? '').trim(),
          code: (raw.code ?? '').trim(),
          semester: raw.semester as number,
          whatsapp,
        }).toPromise();
        this.toast.add({
          severity: 'success',
          summary: 'Estudiante creado',
          detail: 'Clave temporal enviada al correo',
          life: 3500,
        });
      } else {
        await this.api.updateAccount(studentId, {
          full_name: fullName,
          whatsapp,
          is_active: raw.is_active ?? true,
          semester: raw.semester ?? undefined,
        }).toPromise();
        this.toast.add({ severity: 'success', summary: 'Estudiante actualizado', life: 2500 });
      }
      this.dialogVisible = false;
      void this.load();
    } catch (err) {
      this.toast.add({
        severity: 'error',
        summary: 'No se pudo guardar',
        detail: extractDetail(err),
        life: 4500,
      });
    } finally {
      this.saving.set(false);
    }
  }

  private async load(): Promise<void> {
    this.loading.set(true);
    this.error.set(null);
    try {
      const res = await this.api.students({
        page: this.page(), page_size: this.pageSize(), q: this.q(),
        semester: this.semesterNumber() ?? undefined,
        with_face: 'true',
      }).toPromise();
      this.students.set(res?.items ?? []);
      this.total.set(res?.total ?? 0);
    } catch (err) {
      this.error.set(extractDetail(err));
    } finally {
      this.loading.set(false);
    }
  }
}
