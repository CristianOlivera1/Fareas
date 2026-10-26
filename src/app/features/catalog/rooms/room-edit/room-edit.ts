import {
  ChangeDetectionStrategy,
  Component,
  CUSTOM_ELEMENTS_SCHEMA,
  inject,
  input,
  model,
  OnInit,
  output,
  signal,
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MessageService } from 'primeng/api';
import { DialogModule } from 'primeng/dialog';
import { ToggleSwitchModule } from 'primeng/toggleswitch';
import { Room } from '../../../../core/models/catalog';
import { CatalogApi } from '../../../../core/services/catalog-api';
import { extractDetail } from '../../../../shared/utils/api-error';
import { UiButton } from '../../../../shared/components/ui-button/ui-button';
import { UiInput } from '../../../../shared/components/ui-input/ui-input';

interface RoomEditForm {
  name: string;
  building: string;
  is_active: boolean;
}

@Component({
  selector: 'app-room-edit',
  imports: [FormsModule, DialogModule, ToggleSwitchModule, UiButton, UiInput],
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  templateUrl: './room-edit.html',
  styleUrl: './room-edit.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class RoomEdit implements OnInit {
  readonly room = input.required<Room>();
  readonly alwaysVisible = input(false);
  /** Abre el diálogo al crearse, para editarlo desde el plano. */
  readonly autoOpen = input(false);
  readonly visible = model(false);
  readonly saved = output<void>();
  readonly saving = signal(false);
  readonly form = signal<RoomEditForm>({ name: '', building: '', is_active: true });

  private readonly api = inject(CatalogApi);
  private readonly toast = inject(MessageService);

  ngOnInit(): void {
    if (this.autoOpen()) this.open();
  }

  open(): void {
    const room = this.room();
    this.form.set({
      name: room.name ?? '',
      building: room.building ?? '',
      is_active: room.is_active,
    });
    this.visible.set(true);
  }

  patch(patch: Partial<RoomEditForm>): void {
    this.form.update((form) => ({ ...form, ...patch }));
  }

  async save(): Promise<void> {
    this.saving.set(true);
    try {
      const form = this.form();
      await this.api
        .updateRoom(this.room().id, {
          name: form.name,
          building: form.building,
          is_active: form.is_active,
        })
        .toPromise();
      this.toast.add({ severity: 'success', summary: 'Aula actualizada', life: 2500 });
      this.visible.set(false);
      this.saved.emit();
    } catch (err) {
      this.toast.add({
        severity: 'error',
        summary: 'No se pudo guardar',
        detail: extractDetail(err),
        life: 4000,
      });
    } finally {
      this.saving.set(false);
    }
  }
}
