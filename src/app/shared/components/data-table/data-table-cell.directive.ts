import { Directive, TemplateRef, inject, input } from '@angular/core';

@Directive({
  selector: '[appCell]',
})
export class DataTableCellDirective {
  readonly appCell = input.required<string>();
  readonly template = inject(TemplateRef);
}
