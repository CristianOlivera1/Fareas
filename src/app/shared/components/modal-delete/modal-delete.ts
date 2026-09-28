import {
  ChangeDetectionStrategy,
  Component,
  CUSTOM_ELEMENTS_SCHEMA,
  computed,
  input,
  model,
  output,
  signal,
} from '@angular/core';
import { DialogModule } from 'primeng/dialog';

import { UiButton } from '../ui-button/ui-button';

@Component({
  selector: 'app-modal-delete',
  imports: [DialogModule, UiButton],
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  templateUrl: './modal-delete.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ModalDelete {
  readonly visible = model(false);

  readonly itemLabel = input<string | null>(null);
  readonly entityName = input('registro');
  readonly softDelete = input(true);
  readonly loading = input(false);
  readonly warning = input<string | null>(null);

  readonly confirmed = output<void>();
  readonly canceled = output<void>();

  readonly working = signal(false);

  readonly title = computed(() =>
    `${this.softDelete() ? 'Desactivar' : 'Eliminar'} ${this.entityName()}`,
  );

  readonly question = computed(() => {
    const item = this.itemLabel() ? ` «${this.itemLabel()}»` : '';
    return this.softDelete()
      ? `¿Seguro que deseas desactivar${item}? Dejará de aparecer en las operaciones del sistema y podrás reactivarlo después.`
      : `¿Seguro que deseas eliminar${item}? Esta acción no se puede deshacer.`;
  });

  requestClose(value: boolean): void {
    if (this.loading() && value) return;
    this.visible.set(value);
  }

  onConfirm(): void {
    this.working.set(true);
    this.confirmed.emit();
  }

  done(): void {
    this.working.set(false);
  }
}
