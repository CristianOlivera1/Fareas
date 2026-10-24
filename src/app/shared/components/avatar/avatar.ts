import {
  ChangeDetectionStrategy,
  Component,
  computed,
  effect,
  input,
  signal,
} from '@angular/core';

export type AvatarSize = 'sm' | 'md' | 'lg' | 'xl';

const SIZE_CLASSES: Record<AvatarSize, string> = {
  sm: 'size-8 text-xs',
  md: 'size-10 text-sm',
  lg: 'size-12 text-base',
  xl: 'size-20 text-2xl',
};

export function initialsOf(name: string | null | undefined): string {
  const parts = (name ?? '').trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return 'U';
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return `${parts[0][0]}${parts[1][0]}`.toUpperCase();
}

@Component({
  selector: 'app-avatar',
  template: `
    @if (showImage()) {
      <img [src]="src()" [alt]="name() ? 'Foto de ' + name() : 'Foto de perfil'" (error)="failed.set(true)"
        class="size-full rounded-full object-cover" />
    } @else {
      <span aria-hidden="true">{{ initials() }}</span>
    }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: {
    '[class]': 'hostClass()',
    '[attr.role]': 'showImage() ? null : "img"',
    '[attr.aria-label]': 'showImage() ? null : name()',
  },
})
export class Avatar {
  readonly name = input<string | null>(null);
  readonly src = input<string | null>(null);
  readonly size = input<AvatarSize>('md');

  protected readonly failed = signal(false);
  protected readonly initials = computed(() => initialsOf(this.name()));
  protected readonly showImage = computed(() => !!this.src() && !this.failed());
  protected readonly hostClass = computed(
    () =>
      `inline-flex shrink-0 items-center justify-center rounded-full bg-(--fareas-primary) font-bold text-white ${SIZE_CLASSES[this.size()]}`,
  );

  constructor() {
    effect(() => {
      this.src();
      this.failed.set(false);
    });
  }
}
