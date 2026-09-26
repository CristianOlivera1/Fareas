import { ChangeDetectionStrategy, Component, CUSTOM_ELEMENTS_SCHEMA, input } from '@angular/core';

@Component({
  selector: 'app-ui-card',
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  templateUrl: './ui-card.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { class: 'block' },
})
export class UiCard {
  readonly title = input('');
  readonly value = input('');
  readonly detail = input('');
  readonly icon = input('material-symbols:dashboard-outline');
  readonly accent = input('text-(--fareas-primary)');
}
