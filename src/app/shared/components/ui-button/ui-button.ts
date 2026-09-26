import {
  ChangeDetectionStrategy,
  Component,
  CUSTOM_ELEMENTS_SCHEMA,
  computed,
  input,
} from '@angular/core';

export type UiButtonVariant = 'primary' | 'secondary' | 'outline' | 'ghost' | 'danger';
export type UiButtonSize = 'sm' | 'md' | 'lg';

const VARIANT_CLASSES: Record<UiButtonVariant, string> = {
  primary:
    'bg-(--fareas-primary) text-white hover:bg-(--fareas-primary-deep) focus:ring-(--fareas-primary) shadow-2xs',
  secondary: 'bg-gray-100 text-gray-700 hover:bg-gray-200 focus:ring-gray-400',
  outline:
    'border border-gray-300 bg-white text-gray-700 hover:bg-gray-50 focus:ring-(--fareas-primary)',
  ghost: 'text-gray-600 hover:bg-gray-100 hover:text-gray-900 focus:ring-gray-300',
  danger: 'bg-red-600 text-white hover:bg-red-700 focus:ring-red-500 shadow-2xs',
};

const SIZE_CLASSES: Record<UiButtonSize, string> = {
  sm: 'px-3 py-1.5 text-xs',
  md: 'px-4 py-2.5 text-sm',
  lg: 'px-6 py-3 text-base',
};

@Component({
  selector: 'app-ui-button',
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  templateUrl: './ui-button.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { class: 'block' },
})
export class UiButton {
  readonly variant = input<UiButtonVariant>('primary');
  readonly size = input<UiButtonSize>('md');
  readonly type = input<'button' | 'submit'>('button');
  readonly disabled = input(false);
  readonly loading = input(false);
  readonly icon = input<string | null>(null);
  readonly fullWidth = input(false);

  readonly classes = computed(() =>
    [
      'inline-flex items-center justify-center gap-2 font-medium rounded-lg transition-all',
      'focus:outline-none focus:ring-2 focus:ring-offset-2',
      'disabled:opacity-50 disabled:cursor-not-allowed disabled:active:scale-100',
      'active:scale-[0.98]',
      VARIANT_CLASSES[this.variant()],
      SIZE_CLASSES[this.size()],
      this.fullWidth() ? 'w-full' : '',
    ].join(' '),
  );
}
