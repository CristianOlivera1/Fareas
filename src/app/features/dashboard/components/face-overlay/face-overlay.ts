import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  ElementRef,
  effect,
  inject,
  input,
  viewChild,
} from '@angular/core';

import { environment } from '../../../../../environments/environment';
import {
  DETECTED_BOX_COLOR,
  NormalizedBox,
  VERDICT_BOX_COLORS,
  containedFrame,
  easeBox,
  toCanvasBox,
} from '../../../../shared/utils/face-box';

interface FacesEvent {
  boxes: NormalizedBox[];
  verdict: string | null;
  label: string | null;
}

const EASE_FACTOR = 0.35;
const STALE_MS = 700;

@Component({
  selector: 'app-face-overlay',
  templateUrl: './face-overlay.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { class: 'pointer-events-none absolute inset-0 block' },
})
export class FaceOverlay {
  readonly roomId = input.required<number>();
  readonly token = input.required<string>();
  readonly video = input.required<HTMLVideoElement | null>();

  private readonly canvas = viewChild.required<ElementRef<HTMLCanvasElement>>('canvas');
  private source: EventSource | null = null;
  private latest: FacesEvent | null = null;
  private receivedAt = 0;
  private shown: NormalizedBox[] = [];
  private frameId = 0;

  constructor() {
    inject(DestroyRef).onDestroy(() => this.close());

    effect(() => {
      const room = this.roomId();
      const token = this.token();
      this.close();
      if (typeof EventSource === 'undefined') return;
      const url = `${environment.apiUrl}/dashboard/camera/${room}/faces?access_token=${encodeURIComponent(token)}`;
      const source = new EventSource(url);
      source.addEventListener('faces', (event) => {
        this.latest = JSON.parse((event as MessageEvent<string>).data) as FacesEvent;
        this.receivedAt = performance.now();
      });
      this.source = source;
      this.frameId = requestAnimationFrame(() => this.render());
    });
  }

  private close(): void {
    this.source?.close();
    this.source = null;
    cancelAnimationFrame(this.frameId);
    this.latest = null;
    this.shown = [];
  }

  private render(): void {
    this.draw();
    if (this.source) this.frameId = requestAnimationFrame(() => this.render());
  }

  private draw(): void {
    const canvas = this.canvas().nativeElement;
    const ratio = window.devicePixelRatio || 1;
    const width = canvas.clientWidth;
    const height = canvas.clientHeight;
    if (canvas.width !== Math.round(width * ratio) || canvas.height !== Math.round(height * ratio)) {
      canvas.width = Math.round(width * ratio);
      canvas.height = Math.round(height * ratio);
    }
    const context = canvas.getContext('2d');
    if (!context) return;
    context.setTransform(ratio, 0, 0, ratio, 0, 0);
    context.clearRect(0, 0, width, height);

    const event = this.latest;
    if (!event || performance.now() - this.receivedAt > STALE_MS || event.boxes.length === 0) {
      this.shown = [];
      return;
    }
    const video = this.video();
    const frame = containedFrame(width, height, video?.videoWidth ?? 0, video?.videoHeight ?? 0);
    this.shown = event.boxes.map((box, index) =>
      this.shown[index] ? easeBox(this.shown[index], box, EASE_FACTOR) : box,
    );
    this.shown.forEach((box, index) => {
      const color =
        index === 0 && event.verdict ? (VERDICT_BOX_COLORS[event.verdict] ?? DETECTED_BOX_COLOR) : DETECTED_BOX_COLOR;
      this.drawFace(context, toCanvasBox(box, frame), color, index === 0 ? event.label : null);
    });
  }

  private drawFace(
    context: CanvasRenderingContext2D,
    [x1, y1, x2, y2]: NormalizedBox,
    color: string,
    label: string | null,
  ): void {
    const arm = Math.max(10, Math.min(x2 - x1, y2 - y1) * 0.22);
    context.strokeStyle = color;
    context.lineWidth = 1;
    context.strokeRect(x1, y1, x2 - x1, y2 - y1);
    context.lineWidth = 3;
    context.lineCap = 'round';
    context.beginPath();
    for (const [cx, cy, dx, dy] of [
      [x1, y1, 1, 1],
      [x2, y1, -1, 1],
      [x1, y2, 1, -1],
      [x2, y2, -1, -1],
    ]) {
      context.moveTo(cx + dx * arm, cy);
      context.lineTo(cx, cy);
      context.lineTo(cx, cy + dy * arm);
    }
    context.stroke();
    if (!label) return;
    context.font = '600 12px system-ui, sans-serif';
    const textWidth = context.measureText(label).width;
    const top = y1 - 24 < 0 ? y2 + 4 : y1 - 24;
    context.fillStyle = color;
    context.fillRect(x1, top, textWidth + 12, 20);
    context.fillStyle = '#ffffff';
    context.fillText(label, x1 + 6, top + 14);
  }
}
