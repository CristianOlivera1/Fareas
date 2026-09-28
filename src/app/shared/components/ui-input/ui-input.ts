import {
  ChangeDetectionStrategy,
  Component,
  CUSTOM_ELEMENTS_SCHEMA,
  computed,
  forwardRef,
  input,
  signal,
} from '@angular/core';
import { ControlValueAccessor, NG_VALUE_ACCESSOR } from '@angular/forms';

let nextId = 0;

@Component({
  selector: 'app-ui-input',
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  templateUrl: './ui-input.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { class: 'block' },
  providers: [
    {
      provide: NG_VALUE_ACCESSOR,
      useExisting: forwardRef(() => UiInput),
      multi: true,
    },
  ],
})
export class UiInput implements ControlValueAccessor {
  readonly label = input('');
  readonly placeholder = input('');
  readonly type = input('text');
  readonly icon = input<string | null>(null);
  readonly error = input('');
  readonly hint = input('');
  readonly autocomplete = input<string | null>(null);
  readonly customId = input<string | null>(null);
  readonly showPasswordToggle = input(false);
  readonly required = input(false);
  readonly mono = input(false);

  readonly value = signal('');
  readonly disabled = signal(false);
  protected readonly passwordVisible = signal(false);

  private readonly autoId = `ui-input-${++nextId}`;

  readonly resolvedId = computed(() => this.customId() ?? this.autoId);
  readonly showToggle = computed(() => this.type() === 'password' && this.showPasswordToggle());
  readonly effectiveType = computed(() =>
    this.showToggle() && this.passwordVisible() ? 'text' : this.type(),
  );

  private onChange: (value: string) => void = () => {};
  private onTouched: () => void = () => {};

  writeValue(value: string | null): void {
    this.value.set(value ?? '');
  }

  registerOnChange(fn: (value: string) => void): void {
    this.onChange = fn;
  }

  registerOnTouched(fn: () => void): void {
    this.onTouched = fn;
  }

  setDisabledState(isDisabled: boolean): void {
    this.disabled.set(isDisabled);
  }

  protected onInput(event: Event): void {
    const next = (event.target as HTMLInputElement).value;
    this.value.set(next);
    this.onChange(next);
  }

  protected onBlur(): void {
    this.onTouched();
  }

  protected togglePasswordVisibility(): void {
    this.passwordVisible.update((visible) => !visible);
  }
}
