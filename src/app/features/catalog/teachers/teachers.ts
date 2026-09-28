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

interface TeacherForm {
  id: number | null;
  full_name: string;
  email: string;
  dni: string;
  whatsapp: string;
  is_active: boolean;
}

@Component({
  selector: 'app-teachers-page',
  imports: [
    FormsModule, PageHeader, UiButton, UiInput, UiAlert, DataTable, DataTableCellDirective,
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

  readonly form = signal<TeacherForm>({
    id: null, full_name: '', email: '', dni: '', whatsapp: '', is_active: true,
  });

  dialogVisible = false;

  constructor() {
    effect(() => {
      this.q(); this.page(); this.pageSize();
      void this.load();
    });
  }

  patch(p: Partial<TeacherForm>): void {
    this.form.update((f) => ({ ...f, ...p }));
  }

  onSearch(value: string): void { void this.qp.update({ q: value || null, page: null }); }
  onPage(p: number): void { void this.qp.update({ page: p }); }
  onPageSize(s: number): void { void this.qp.update({ page_size: s, page: null }); }
  reload(): void { void this.load(); }

  openCreate(): void {
    this.form.set({ id: null, full_name: '', email: '', dni: '', whatsapp: '', is_active: true });
    this.dialogVisible = true;
  }

  openEdit(p: Person): void {
    this.form.set({
      id: p.id, full_name: p.full_name, email: p.email, dni: p.dni ?? '',
      whatsapp: p.whatsapp ?? '', is_active: p.is_active,
    });
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
    const f = this.form();
    this.saving.set(true);
    try {
      if (f.id === null) {
        if (!f.full_name.trim() || !f.email.trim() || f.dni.trim().length !== 8) {
          this.toast.add({ severity: 'warn', summary: 'Completa nombre, correo y DNI (8 dígitos)', life: 3000 });
          return;
        }
        await this.api.createTeacher({
          full_name: f.full_name.trim(), email: f.email.trim().toLowerCase(),
          dni: f.dni.trim(), whatsapp: f.whatsapp || null,
        }).toPromise();
        this.toast.add({ severity: 'success', summary: 'Docente creado', detail: 'Clave temporal enviada al correo', life: 3500 });
      } else {
        await this.api.updateAccount(f.id, {
          full_name: f.full_name.trim(), whatsapp: f.whatsapp || null, is_active: f.is_active,
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
