import {
  ChangeDetectionStrategy,
  Component,
  CUSTOM_ELEMENTS_SCHEMA,
  DestroyRef,
  ElementRef,
  computed,
  inject,
  signal,
  viewChild,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute } from '@angular/router';
import { MessageService } from 'primeng/api';
import { Subject, debounceTime, distinctUntilChanged, firstValueFrom } from 'rxjs';

import { Person } from '../../../core/models/catalog';
import { FaceStatus } from '../../../core/models/faces';
import { CatalogApi } from '../../../core/services/catalog-api';
import { FacesApi } from '../../../core/services/faces-api';
import { ModalDelete } from '../../../shared/components/modal-delete/modal-delete';
import { PageHeader } from '../../../shared/components/page-header/page-header';
import { UiAlert } from '../../../shared/components/ui-alert/ui-alert';
import { UiButton } from '../../../shared/components/ui-button/ui-button';
import { UiInput } from '../../../shared/components/ui-input/ui-input';
import { extractDetail } from '../../../shared/utils/api-error';

const MIN_PHOTOS = 3;
const MAX_PHOTOS = 5;
const CAPTURE_WIDTH = 640;
const MAX_FILE_BYTES = 8 * 1024 * 1024;
const POSES = [
  'Mira al frente',
  'Gira levemente a la izquierda',
  'Gira levemente a la derecha',
  'Sonríe',
];

@Component({
  selector: 'app-faces-page',
  imports: [
    FormsModule,
    PageHeader,
    UiButton,
    UiInput,
    UiAlert,
    ModalDelete,
  ],
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  templateUrl: './faces-page.html',
  styleUrl: './faces-page.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class FacesPage {
  private readonly api = inject(FacesApi);
  private readonly catalog = inject(CatalogApi);
  private readonly route = inject(ActivatedRoute);
  private readonly toast = inject(MessageService);
  private readonly destroyRef = inject(DestroyRef);
  private readonly deleteModal = viewChild(ModalDelete);
  private readonly videoRef = viewChild<ElementRef<HTMLVideoElement>>('video');

  readonly minPhotos = MIN_PHOTOS;
  readonly maxPhotos = MAX_PHOTOS;
  readonly slots = Array.from({ length: MAX_PHOTOS }, (_, index) => index);

  readonly search = signal('');
  readonly results = signal<Person[]>([]);
  readonly searching = signal(false);
  readonly selected = signal<Person | null>(null);
  readonly status = signal<FaceStatus | null>(null);
  readonly loadingStatus = signal(false);

  readonly photos = signal<string[]>([]);
  readonly consent = signal(false);
  readonly saving = signal(false);
  readonly error = signal<string | null>(null);
  readonly success = signal<string | null>(null);

  readonly cameraActive = signal(false);
  readonly cameraBusy = signal(false);
  readonly cameraError = signal<string | null>(null);

  deleteVisible = false;
  readonly deleting = signal(false);

  readonly canSubmit = computed(
    () =>
      this.selected() !== null &&
      this.photos().length >= MIN_PHOTOS &&
      this.consent() &&
      !this.saving(),
  );
  readonly nextPose = computed(
    () => POSES[Math.min(this.photos().length, POSES.length - 1)],
  );
  readonly photoHint = computed(() => {
    const count = this.photos().length;
    if (count < MIN_PHOTOS) return `Faltan ${MIN_PHOTOS - count} foto(s) para el mínimo.`;
    if (count < MAX_PHOTOS) return `Puedes añadir hasta ${MAX_PHOTOS - count} foto(s) más.`;
    return 'Llegaste al máximo de fotos.';
  });

  private stream: MediaStream | null = null;
  private readonly search$ = new Subject<string>();

  constructor() {
    this.search$
      .pipe(debounceTime(300), distinctUntilChanged(), takeUntilDestroyed(this.destroyRef))
      .subscribe((query) => void this.searchStudents(query));

    this.destroyRef.onDestroy(() => this.stopCamera());

    const initial = Number(this.route.snapshot.queryParamMap.get('student'));
    if (Number.isInteger(initial) && initial > 0) {
      void this.selectById(initial);
    }
    void this.searchStudents('');
  }

  onSearch(value: string): void {
    this.search.set(value);
    this.search$.next(value.trim());
  }

  initials(name: string): string {
    const parts = name.trim().split(/\s+/);
    return parts.length >= 2
      ? `${parts[0][0]}${parts[1][0]}`.toUpperCase()
      : name.slice(0, 2).toUpperCase();
  }

  async select(person: Person): Promise<void> {
    this.stopCamera();
    this.selected.set(person);
    this.status.set(null);
    this.photos.set([]);
    this.consent.set(false);
    this.error.set(null);
    this.success.set(null);
    await this.loadStatus(person.id);
  }

  async reloadStatus(): Promise<void> {
    const person = this.selected();
    if (person) await this.loadStatus(person.id);
  }

  async startCamera(): Promise<void> {
    if (this.cameraActive() || this.cameraBusy()) return;
    this.cameraError.set(null);
    if (!navigator.mediaDevices?.getUserMedia) {
      this.cameraError.set(
        'Este navegador no permite usar la cámara. Sube las fotos desde un archivo.',
      );
      return;
    }

    this.cameraBusy.set(true);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: 'user', width: { ideal: 1280 }, height: { ideal: 720 } },
        audio: false,
      });
      this.stream = stream;
      this.cameraActive.set(true);
      await this.attachStream();
    } catch (err) {
      this.cameraError.set(this.cameraMessage(err));
    } finally {
      this.cameraBusy.set(false);
    }
  }

  stopCamera(): void {
    this.stream?.getTracks().forEach((track) => track.stop());
    this.stream = null;
    const video = this.videoRef()?.nativeElement;
    if (video) video.srcObject = null;
    this.cameraActive.set(false);
  }

  capture(): void {
    const video = this.videoRef()?.nativeElement;
    if (!video || !video.videoWidth) {
      this.cameraError.set('La cámara todavía no está lista; espera un momento.');
      return;
    }
    if (this.photos().length >= MAX_PHOTOS) {
      this.warn(`Ya tienes ${MAX_PHOTOS} fotos; elimina una para cambiar la toma.`);
      return;
    }

    const canvas = document.createElement('canvas');
    const scale = Math.min(1, CAPTURE_WIDTH / video.videoWidth);
    canvas.width = Math.round(video.videoWidth * scale);
    canvas.height = Math.round(video.videoHeight * scale);
    const context = canvas.getContext('2d');
    if (!context) return;
    context.drawImage(video, 0, 0, canvas.width, canvas.height);
    this.addPhoto(canvas.toDataURL('image/jpeg', 0.85));
  }

  removePhoto(index: number): void {
    this.photos.update((list) => list.filter((_, i) => i !== index));
    this.error.set(null);
  }

  async onFilesSelected(event: Event): Promise<void> {
    const input = event.target as HTMLInputElement;
    const files = Array.from(input.files ?? []);
    input.value = '';

    for (const file of files) {
      if (this.photos().length >= MAX_PHOTOS) {
        this.warn(`El máximo es ${MAX_PHOTOS} fotos por enrolamiento.`);
        return;
      }
      if (!['image/jpeg', 'image/png'].includes(file.type)) {
        this.error.set(`“${file.name}” no es JPG ni PNG.`);
        continue;
      }
      if (file.size > MAX_FILE_BYTES) {
        this.error.set(`“${file.name}” supera los 8 MB.`);
        continue;
      }
      try {
        this.addPhoto(await this.compress(file));
      } catch {
        this.error.set(`No se pudo leer “${file.name}”; intenta con otra foto.`);
      }
    }
  }

  async submit(): Promise<void> {
    const person = this.selected();
    if (!person || !this.canSubmit()) return;

    this.saving.set(true);
    this.error.set(null);
    this.success.set(null);
    try {
      const result = await firstValueFrom(
        this.api.enroll(person.id, this.photos(), true),
      );
      this.success.set(
        `Rostro enrolado con ${result.photos} fotos (consistencia ${Math.round(
          result.min_pair_similarity * 100,
        )} %).`,
      );
      this.toast.add({
        severity: 'success',
        summary: 'Rostro enrolado',
        detail: `${person.full_name} ya puede registrarse en las cámaras.`,
        life: 4500,
      });
      this.photos.set([]);
      this.consent.set(false);
      this.stopCamera();
      await this.loadStatus(person.id);
    } catch (err) {
      this.error.set(extractDetail(err));
    } finally {
      this.saving.set(false);
    }
  }

  askDelete(): void {
    this.deleteVisible = true;
  }

  async confirmDelete(): Promise<void> {
    const person = this.selected();
    if (!person) return;

    this.deleting.set(true);
    try {
      const result = await firstValueFrom(this.api.remove(person.id));
      this.toast.add({
        severity: 'success',
        summary: 'Rostro eliminado',
        detail: `Se borraron ${result.deleted} registro(s) biométrico(s).`,
        life: 4500,
      });
      this.photos.set([]);
      this.consent.set(false);
      this.success.set(null);
      await this.loadStatus(person.id);
    } catch (err) {
      this.toast.add({
        severity: 'error',
        summary: 'No se pudo eliminar el rostro',
        detail: extractDetail(err),
        life: 4500,
      });
    } finally {
      this.deleteModal()?.done();
      this.deleting.set(false);
      this.deleteVisible = false;
    }
  }

  formatDate(value: string | null): string {
    if (!value) return '';
    return new Date(value).toLocaleString('es-PE', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  }

  private async selectById(studentId: number): Promise<void> {
    try {
      const person = await firstValueFrom(this.catalog.account(studentId));
      await this.select(person);
    } catch (err) {
      this.error.set(extractDetail(err));
      void this.searchStudents('');
    }
  }

  private async searchStudents(query: string): Promise<void> {
    this.searching.set(true);
    try {
      const page = await firstValueFrom(
        this.catalog.students({
          q: query || undefined,
          page_size: 8,
          with_face: 'true',
        }),
      );
      this.results.set(page.items);
    } catch (err) {
      this.error.set(extractDetail(err));
    } finally {
      this.searching.set(false);
    }
  }

  private async loadStatus(studentId: number): Promise<void> {
    this.loadingStatus.set(true);
    try {
      this.status.set(await firstValueFrom(this.api.status(studentId)));
    } catch (err) {
      this.error.set(extractDetail(err));
    } finally {
      this.loadingStatus.set(false);
    }
  }

  private addPhoto(dataUrl: string): void {
    if (this.photos().length >= MAX_PHOTOS) return;
    this.photos.update((list) => [...list, dataUrl]);
    this.error.set(null);
    this.success.set(null);
  }

  private async compress(file: File): Promise<string> {
    const bitmap = await createImageBitmap(file);
    try {
      const scale = Math.min(1, CAPTURE_WIDTH / bitmap.width);
      const canvas = document.createElement('canvas');
      canvas.width = Math.round(bitmap.width * scale);
      canvas.height = Math.round(bitmap.height * scale);
      const context = canvas.getContext('2d');
      if (!context) throw new Error('canvas');
      context.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
      return canvas.toDataURL('image/jpeg', 0.85);
    } finally {
      bitmap.close();
    }
  }

  private async attachStream(): Promise<void> {
    for (let attempt = 0; attempt < 10; attempt++) {
      const video = this.videoRef()?.nativeElement;
      if (video) {
        video.srcObject = this.stream;
        await video.play().catch(() => undefined);
        return;
      }
      await new Promise((resolve) => setTimeout(resolve, 50));
    }
  }

  private cameraMessage(err: unknown): string {
    const name = (err as DOMException | undefined)?.name;
    if (name === 'NotAllowedError') {
      return 'Permiso de cámara denegado. Habilítalo en el navegador o sube las fotos.';
    }
    if (name === 'NotFoundError') {
      return 'No se encontró una cámara. Sube las fotos desde archivos.';
    }
    if (name === 'NotReadableError') {
      return 'La cámara está siendo usada por otra aplicación.';
    }
    return 'No se pudo activar la cámara. Sube las fotos desde archivos.';
  }

  private warn(detail: string): void {
    this.toast.add({ severity: 'warn', summary: 'Fotos', detail, life: 3000 });
  }
}
