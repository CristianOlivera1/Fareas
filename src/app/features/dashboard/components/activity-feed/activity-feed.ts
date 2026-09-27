import {
  ChangeDetectionStrategy,
  Component,
  CUSTOM_ELEMENTS_SCHEMA,
  DestroyRef,
  inject,
  signal,
} from '@angular/core';

interface IdentifiedPerson {
  name: string;
  code: string;
  group: string;
  course: string;
  room: string;
  camera: string;
  /** Similitud del embedding en % (RF-20: umbral mínimo 75%). */
  similarity: number;
  /** Veredicto mostrado en la puerta (RF-25 / Tabla 8). */
  verdict: 'Asistió' | 'Tardanza';
  message: string;
  initials: string;
}

/** Detecciones de una misma sesión (LAB 305, misma cámara), coherentes con student-list. */
const MOCK_ROTATION: IdentifiedPerson[] = [
  {
    name: 'Raul Montesinos Valdivia',
    code: '221181',
    group: 'A',
    course: 'Metodología de la Investigación Científica',
    room: 'LAB 305',
    camera: '10.14.5.5',
    similarity: 92.5,
    verdict: 'Asistió',
    message: 'Registro correcto',
    initials: 'RM',
  },
  {
    name: 'Razib Rahman Ttito',
    code: '231204',
    group: 'A',
    course: 'Metodología de la Investigación Científica',
    room: 'LAB 305',
    camera: '10.14.5.5',
    similarity: 97.1,
    verdict: 'Tardanza',
    message: 'Registro con tardanza',
    initials: 'RT',
  },
  {
    name: 'Lucía Fernández Quispe',
    code: '221105',
    group: 'A',
    course: 'Metodología de la Investigación Científica',
    room: 'LAB 305',
    camera: '10.14.5.5',
    similarity: 88.4,
    verdict: 'Asistió',
    message: 'Registro correcto',
    initials: 'LF',
  },
];

function nowTime(): string {
  return new Date().toLocaleTimeString('es-PE', {
    hour: 'numeric',
    minute: '2-digit',
    second: '2-digit',
    hour12: true,
  });
}

@Component({
  selector: 'app-activity-feed',
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  templateUrl: './activity-feed.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { class: 'block' },
})
export class ActivityFeed {
  private index = 0;

  readonly person = signal<IdentifiedPerson>(MOCK_ROTATION[0]);
  readonly detectedAt = signal(nowTime());

  constructor() {
    const destroyRef = inject(DestroyRef);
    const timer = setInterval(() => {
      this.index = (this.index + 1) % MOCK_ROTATION.length;
      this.person.set(MOCK_ROTATION[this.index]);
      this.detectedAt.set(nowTime());
    }, 5000);
    destroyRef.onDestroy(() => clearInterval(timer));
  }

  verdictColor(verdict: IdentifiedPerson['verdict']): string {
    return verdict === 'Asistió' ? 'bg-green-500' : 'bg-amber-500';
  }
}
