import { ChangeDetectionStrategy, Component, CUSTOM_ELEMENTS_SCHEMA, inject } from '@angular/core';
import { ActivatedRoute } from '@angular/router';
import { PageHeader } from '../../shared/components/page-header/page-header';

/** iconify-icon es un Web Component: se declara via CUSTOM_ELEMENTS_SCHEMA. */

/** Placeholder de las rutas creadas en F1; cada bloque posterior (F2-F6)
 * reemplaza este componente por la pantalla real. */
@Component({
  selector: 'app-placeholder-page',
  imports: [PageHeader],
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  template: `
    <app-page-header [title]="title()" subtitle="Disponible en el siguiente bloque del plan" />
    <div class="rounded-xl border border-dashed border-gray-300 bg-white p-10 text-center">
      <iconify-icon icon="material-symbols:construction" width="36" class="text-gray-300"></iconify-icon>
      <p class="mt-3 text-sm text-gray-500">
        Esta pantalla se construye en el bloque
        <span class="font-semibold text-gray-700">{{ block() }}</span> del plan.
      </p>
    </div>
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { class: 'block' },
})
export class PlaceholderPage {
  private readonly route = inject(ActivatedRoute);

  /** data.placeholder = 'F2 · Catálogos' etc. (definido en app.routes.ts) */
  readonly meta = this.route.snapshot.data['placeholder'] as string | undefined;

  title(): string {
    const label = this.route.snapshot.data['title'] as string | undefined;
    return label ?? 'Pantalla';
  }

  block(): string {
    return this.meta ?? 'siguiente';
  }
}
