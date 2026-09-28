import {
  ChangeDetectionStrategy,
  Component,
  CUSTOM_ELEMENTS_SCHEMA,
  effect,
  inject,
  signal,
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MessageService } from 'primeng/api';
import { DialogModule } from 'primeng/dialog';
import { InputTextModule } from 'primeng/inputtext';
import { SelectModule } from 'primeng/select';
import { ToggleSwitchModule } from 'primeng/toggleswitch';
import { QueryParams } from '../../../shared/utils/query-params';
import { CatalogApi } from '../../../core/services/catalog-api';
import { AuthService } from '../../../core/services/auth/auth';
import { PageHeader } from '../../../shared/components/page-header/page-header';
import { UiButton } from '../../../shared/components/ui-button/ui-button';
import { UiInput } from '../../../shared/components/ui-input/ui-input';
import { UiAlert } from '../../../shared/components/ui-alert/ui-alert';
import { DataTable } from '../../../shared/components/data-table/data-table';
import { DataTableCellDirective } from '../../../shared/components/data-table/data-table-cell.directive';
import { TableColumn } from '../../../core/models/table-column';
import { Person } from '../../../core/models/catalog';
import { extractDetail } from '../rooms/rooms';

const CICLOS = Array.from({ length: 12 }, (_, i) => ({ label: `${i + 1}`, value: i + 1 }));

interface StudentForm {
  id: number | null;
  full_name: string;
  email: string;
  dni: string;
  code: string;
  semester: number | null;
  whatsapp: string;
  is_active: boolean;
}

@Component({
  selector: 'app-students-page',
  imports: [
    FormsModule, PageHeader, UiButton, UiInput, UiAlert, DataTable, DataTableCellDirective,
    DialogModule, InputTextModule, SelectModule, ToggleSwitchModule,
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

  readonly ciclos = CICLOS;

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
  readonly page = this.qp.number('page', 1);
  readonly pageSize = this.qp.number('page_size', 10);

  readonly students = signal<Person[]>([]);
  readonly total = signal(0);
  readonly loading = signal(false);
  readonly error = signal<string | null>(null);
  readonly saving = signal(false);

  readonly form = signal<StudentForm>({
    id: null, full_name: '', email: '', dni: '', code: '', semester: null, whatsapp: '', is_active: true,
  });

  dialogVisible = false;

  constructor() {
    effect(() => {
      this.q(); this.semester(); this.page(); this.pageSize();
      void this.load();
    });
  }

  initials(name: string): string {
    const parts = name.trim().split(/\s+/);
    return parts.length >= 2
      ? `${parts[0][0]}${parts[1][0]}`.toUpperCase()
      : name.slice(0, 2).toUpperCase();
  }

  patch(p: Partial<StudentForm>): void {
    this.form.update((f) => ({ ...f, ...p }));
  }

  onSearch(value: string): void { void this.qp.update({ q: value || null, page: null }); }
  onSemester(value: string | number | null): void {
    void this.qp.update({ semester: value ? String(value) : null, page: null });
  }
  onPage(p: number): void { void this.qp.update({ page: p }); }
  onPageSize(s: number): void { void this.qp.update({ page_size: s, page: null }); }
  reload(): void { void this.load(); }

  openCreate(): void {
    this.form.set({ id: null, full_name: '', email: '', dni: '', code: '', semester: null, whatsapp: '', is_active: true });
    this.dialogVisible = true;
  }

  openEdit(s: Person): void {
    this.form.set({
      id: s.id, full_name: s.full_name, email: s.email, dni: s.dni ?? '',
      code: s.code ?? '', semester: s.semester, whatsapp: s.whatsapp ?? '', is_active: s.is_active,
    });
    this.dialogVisible = true;
  }

  async save(): Promise<void> {
    const f = this.form();
    this.saving.set(true);
    try {
      if (f.id === null) {
        if (!f.full_name.trim() || !f.email.trim() || f.dni.trim().length !== 8
            || f.code.trim().length !== 6 || !f.semester) {
          this.toast.add({
            severity: 'warn',
            summary: 'Completa los campos obligatorios',
            detail: 'DNI de 8 dígitos, código de matrícula de 6 y ciclo',
            life: 3500,
          });
          return;
        }
        await this.api.createStudent({
          full_name: f.full_name.trim(), email: f.email.trim().toLowerCase(), dni: f.dni.trim(),
          code: f.code.trim(), semester: f.semester, whatsapp: f.whatsapp || null,
        }).toPromise();
        this.toast.add({ severity: 'success', summary: 'Estudiante creado', detail: 'Clave temporal enviada al correo', life: 3500 });
      } else {
        await this.api.updateAccount(f.id, {
          full_name: f.full_name.trim(), whatsapp: f.whatsapp || null, is_active: f.is_active,
          semester: f.semester ?? undefined,
        }).toPromise();
        this.toast.add({ severity: 'success', summary: 'Estudiante actualizado', life: 2500 });
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
      const res = await this.api.students({
        page: this.page(), page_size: this.pageSize(), q: this.q(),
        semester: this.semester() ? Number(this.semester()) : undefined,
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
