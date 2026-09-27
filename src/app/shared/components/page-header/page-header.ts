import { ChangeDetectionStrategy, Component, CUSTOM_ELEMENTS_SCHEMA, input } from '@angular/core';

/** Encabezado estándar de las páginas del panel (título + acciones a la derecha). */
@Component({
  selector: 'app-page-header',
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  template: `
    <div class="mb-5 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
      <div class="min-w-0">
        <h1 class="truncate text-xl font-semibold tracking-tight text-gray-900">{{ title() }}</h1>
        @if (subtitle()) {
          <p class="mt-0.5 truncate text-sm text-gray-500">{{ subtitle() }}</p>
        }
      </div>
      <div class="flex shrink-0 items-center gap-2">
        <ng-content />
      </div>
    </div>
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { class: 'block' },
})
export class PageHeader {
  readonly title = input.required<string>();
  readonly subtitle = input<string | null>(null);
}
