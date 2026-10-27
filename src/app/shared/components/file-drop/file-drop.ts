import {
  ChangeDetectionStrategy,
  Component,
  CUSTOM_ELEMENTS_SCHEMA,
  input,
  output,
  signal,
} from '@angular/core';

@Component({
  selector: 'app-file-drop',
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  templateUrl: './file-drop.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { class: 'block' },
})
export class FileDrop {
  readonly file = input<File | null>(null);
  readonly accept = input('.pdf,.jpg,.jpeg,.png,.webp');
  readonly maxSizeMb = input(10);
  readonly hint = input('PDF, JPG, PNG o WEBP · máximo 10 MB');
  readonly disabled = input(false);

  readonly fileChange = output<File | null>();
  readonly fileError = output<string>();

  protected readonly dragging = signal(false);

  protected onPicker(event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    input.value = '';
    if (file) this.choose(file);
  }

  protected onDragOver(event: DragEvent): void {
    event.preventDefault();
    if (!this.disabled()) this.dragging.set(true);
  }

  protected onDragLeave(event: DragEvent): void {
    event.preventDefault();
    this.dragging.set(false);
  }

  protected onDrop(event: DragEvent): void {
    event.preventDefault();
    this.dragging.set(false);
    if (this.disabled()) return;
    const file = event.dataTransfer?.files?.[0];
    if (file) this.choose(file);
  }

  protected remove(event: Event): void {
    event.stopPropagation();
    this.fileChange.emit(null);
  }

  protected formatSize(bytes: number): string {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }

  private choose(file: File): void {
    const extension = `.${file.name.split('.').pop()?.toLowerCase() ?? ''}`;
    const allowed = this.accept()
      .split(',')
      .map((value) => value.trim().toLowerCase())
      .filter(Boolean);
    if (allowed.length > 0 && !allowed.includes(extension)) {
      const formats = allowed.map((value) => value.slice(1).toUpperCase()).join(', ');
      this.fileError.emit(`Formato no soportado. Sube un archivo ${formats}.`);
      return;
    }
    if (file.size > this.maxSizeMb() * 1024 * 1024) {
      this.fileError.emit(`El archivo supera el máximo de ${this.maxSizeMb()} MB.`);
      return;
    }
    if (file.size === 0) {
      this.fileError.emit('El archivo está vacío.');
      return;
    }
    this.fileChange.emit(file);
  }
}
