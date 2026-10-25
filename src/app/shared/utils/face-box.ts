export type NormalizedBox = readonly [number, number, number, number];

export interface FrameRect {
  readonly x: number;
  readonly y: number;
  readonly width: number;
  readonly height: number;
}

export function containedFrame(
  containerWidth: number,
  containerHeight: number,
  videoWidth: number,
  videoHeight: number,
): FrameRect {
  if (videoWidth <= 0 || videoHeight <= 0) {
    return { x: 0, y: 0, width: containerWidth, height: containerHeight };
  }
  const scale = Math.min(containerWidth / videoWidth, containerHeight / videoHeight);
  const width = videoWidth * scale;
  const height = videoHeight * scale;
  return { x: (containerWidth - width) / 2, y: (containerHeight - height) / 2, width, height };
}

export function toCanvasBox(box: NormalizedBox, frame: FrameRect): NormalizedBox {
  return [
    frame.x + box[0] * frame.width,
    frame.y + box[1] * frame.height,
    frame.x + box[2] * frame.width,
    frame.y + box[3] * frame.height,
  ];
}

export function easeBox(current: NormalizedBox, target: NormalizedBox, factor: number): NormalizedBox {
  return [
    current[0] + (target[0] - current[0]) * factor,
    current[1] + (target[1] - current[1]) * factor,
    current[2] + (target[2] - current[2]) * factor,
    current[3] + (target[3] - current[3]) * factor,
  ];
}

export const VERDICT_BOX_COLORS: Record<string, string> = {
  asistio: '#3cc850',
  tardanza: '#f0be1e',
  denegado: '#e63c3c',
  desconocido: '#2896e6',
  sin_registro: '#2896e6',
  verificando: '#2896e6',
};

export const DETECTED_BOX_COLOR = '#3cc850';
