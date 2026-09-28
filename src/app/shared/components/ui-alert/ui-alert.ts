import {
  ChangeDetectionStrategy,
  Component,
  CUSTOM_ELEMENTS_SCHEMA,
  computed,
  input,
  output,
  signal,
} from '@angular/core';

export type UiAlertVariant = 'info' | 'success' | 'warning' | 'danger';

const VARIANT_CLASSES: Record<UiAlertVariant, { box: string; icon: string; iconColor: string; title: string }> = {
  info: {
    box: 'border-blue-200 bg-blue-50',
    icon: 'material-symbols:info-outline',
    iconColor: 'text-(--fareas-primary)',
    title: 'text-blue-900',
  },
  success: {
    box: 'border-green-200 bg-green-50',
    icon: 'material-symbols:check-circle-outline',
    iconColor: 'text-green-600',
    title: 'text-green-900',
  },
  warning: {
    box: 'border-amber-200 bg-amber-50',
    icon: 'material-symbols:warning-outline',
    iconColor: 'text-amber-600',
    title: 'text-amber-900',
  },
  danger: {
    box: 'border-red-200 bg-red-50',
    icon: 'material-symbols:error-outline',
    iconColor: 'text-red-600',
    title: 'text-red-900',
  },
};

@Component({
  selector: 'app-ui-alert',
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  templateUrl: './ui-alert.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { class: 'block' },
})
export class UiAlert {
  readonly variant = input<UiAlertVariant>('info');
  readonly title = input<string | null>(null);
  readonly icon = input<string | null>(null);
  readonly dismissible = input(false);
  readonly inline = input(false);
  readonly dismissed = signal(false);
  readonly dismissedChange = output<void>();

  readonly classes = computed(() => {
    const v = VARIANT_CLASSES[this.variant()];
    if (this.inline()) {
      return { box: '', icon: v.icon, iconColor: v.iconColor, title: v.title };
    }
    return { box: v.box, icon: v.icon, iconColor: v.iconColor, title: v.title };
  });

  dismiss(): void {
    this.dismissed.set(true);
    this.dismissedChange.emit();
  }
}
