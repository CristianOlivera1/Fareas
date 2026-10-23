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
import { FormsModule } from '@angular/forms';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import {
  FormBuilder,
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

@Component({
  selector: 'app-teachers-page',
  imports: [
    FormsModule, ReactiveFormsModule, PageHeader, UiButton, UiInput, UiAlert, DataTable, DataTableCellDirective,
    DialogModule, InputTextModule, ToggleSwitchModule,
  ],
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  templateUrl: './teachers.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class TeachersPage {
  protected readonly auth = inject(AuthService);
  private readonly api = inject(CatalogApi);
  private readonly qp = inject(QueryParams);
  private readonly toast = inject(MessageService);
  private readonly fb = inject(FormBuilder);
  private readonly destroyRef = inject(DestroyRef);

  readonly teacherId = signal<number | null>(null);
  readonly isEditing = computed(() => this.teacherId() !== null);
  readonly teacherForm = this.fb.group({
    full_name: ['', [Validators.required, nonBlank, Validators.minLength(3), Validators.maxLength(160)]],
    email: ['', [
      Validators.required,
      Validators.email,
      institutionalEmail,
      Validators.maxLength(160),
    ]],
    dni: ['', [Validators.required, Validators.pattern(DNI_PATTERN)]],
    whatsapp: ['', [peruWhatsapp, Validators.maxLength(20)]],
    is_active: [true],
  });

  readonly columns: TableColumn[] = [
    { id: 'index', header: 'N°', width: '60px', align: 'center' },
    { id: 'full_name', header: 'Docente' },
    { id: 'email', header: 'Correo', hiddenOnMobile: true },
    { id: 'dni', header: 'DNI', align: 'center', hiddenOnMobile: true },
    { id: 'whatsapp', header: 'WhatsApp', hiddenOnMobile: true },
    { id: 'is_active', header: 'Estado', align: 'center' },
    { id: 'actions', header: 'Acciones', align: 'center', width: '110px' },
  ];

  readonly q = this.qp.filter('q');
  readonly page = this.qp.number('page', 1);
  readonly pageSize = this.qp.number('page_size', 10);

  readonly people = signal<Person[]>([]);
  readonly total = signal(0);
  readonly loading = signal(false);
  readonly error = signal<string | null>(null);
  readonly saving = signal(false);
  readonly resendingId = signal<number | null>(null);

  dialogVisible = false;

  constructor() {
    effect(() => {
      this.q(); this.page(); this.pageSize();
      void this.load();
    });

    this.teacherForm.controls.dni.valueChanges
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((value) => {
        const digits = (value ?? '').replace(/\D/g, '').slice(0, 8);
        if (digits !== value) this.teacherForm.controls.dni.setValue(digits);
      });
  }

  onSearch(value: string): void { void this.qp.update({ q: value || null, page: null }); }
  onPage(p: number): void { void this.qp.update({ page: p }); }
  onPageSize(s: number): void { void this.qp.update({ page_size: s, page: null }); }
  reload(): void { void this.load(); }

  fieldError(field: 'full_name' | 'email' | 'dni' | 'whatsapp'): string {
    const control = this.teacherForm.get(field);
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
    if (control.errors['pattern']) return 'El DNI debe tener exactamente 8 dígitos.';
    if (control.errors['whatsapp']) {
      return 'Ingresa un celular peruano de 9 dígitos que empiece con 9.';
    }
    return 'Valor inválido.';
  }

  openCreate(): void {
    this.teacherId.set(null);
    this.teacherForm.enable();
    this.teacherForm.reset({
      full_name: '', email: '', dni: '', whatsapp: '', is_active: true,
    });
    this.dialogVisible = true;
  }

  openEdit(p: Person): void {
    this.teacherId.set(p.id);
    this.teacherForm.reset({
      full_name: p.full_name,
      email: p.email,
      dni: p.dni ?? '',
      whatsapp: p.whatsapp ?? '',
      is_active: p.is_active,
    });
    this.teacherForm.controls.email.disable();
    this.teacherForm.controls.dni.disable();
    this.dialogVisible = true;
  }

  async resend(p: Person): Promise<void> {
    this.resendingId.set(p.id);
    try {
      const res = await this.api.resendCredentials(p.id).toPromise();
      this.toast.add({ severity: 'success', summary: 'Clave enviada', detail: res?.message, life: 3500 });
    } catch (err) {
      this.toast.add({ severity: 'error', summary: 'No se pudo enviar', detail: extractDetail(err), life: 4000 });
    } finally {
      this.resendingId.set(null);
    }
  }

  async save(): Promise<void> {
    if (this.saving()) return;
    if (this.teacherForm.invalid) {
      this.teacherForm.markAllAsTouched();
      this.toast.add({
        severity: 'warn',
        summary: 'Revisa el formulario',
        detail: 'Corrige los campos marcados antes de guardar.',
        life: 3500,
      });
      return;
    }

    const raw = this.teacherForm.getRawValue();
    const fullName = (raw.full_name ?? '').trim();
    const whatsappValue = (raw.whatsapp ?? '').trim();
    const whatsapp = whatsappValue ? normalizeWhatsapp(whatsappValue) : null;
    const teacherId = this.teacherId();
    this.saving.set(true);
    try {
      if (teacherId === null) {
        await this.api.createTeacher({
          full_name: fullName,
          email: (raw.email ?? '').trim().toLowerCase(),
          dni: (raw.dni ?? '').trim(),
          whatsapp,
        }).toPromise();
        this.toast.add({ severity: 'success', summary: 'Docente creado', detail: 'Clave temporal enviada al correo', life: 3500 });
      } else {
        await this.api.updateAccount(teacherId, {
          full_name: fullName,
          whatsapp,
          is_active: raw.is_active ?? true,
        }).toPromise();
        this.toast.add({ severity: 'success', summary: 'Docente actualizado', life: 2500 });
      }
      this.dialogVisible = false;
      void this.load();
    } catch (err) {
      this.toast.add({ severity: 'error', summary: 'No se pudo guardar', detail: extractDetail(err), life: 4500 });
    } finally {
      this.saving.set(false);
    }
  }

  private async load(): Promise<void> {
    this.loading.set(true);
    this.error.set(null);
    try {
      const res = await this.api.teachers({ page: this.page(), page_size: this.pageSize(), q: this.q() }).toPromise();
      this.people.set(res?.items ?? []);
      this.total.set(res?.total ?? 0);
    } catch (err) {
      this.error.set(extractDetail(err));
    } finally {
      this.loading.set(false);
    }
  }
}
