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
  similarity: number;
  initials: string;
}

const MOCK_ROTATION: IdentifiedPerson[] = [
  {
    name: 'Raul Montesinos Valdivia',
    code: '221181',
    group: 'A',
    course: 'Estructura de datos',
    room: '305',
    camera: '192.5.10.5',
    similarity: 92.5,
    initials: 'RM',
  },
  {
    name: 'Razib Rahman',
    code: '25511',
    group: 'B',
    course: 'Metodología ágil',
    room: '104',
    camera: '192.5.10.8',
    similarity: 97.1,
    initials: 'RR',
  },
  {
    name: 'Luke Norton',
    code: '24447',
    group: 'A',
    course: 'Big data',
    room: '202',
    camera: '192.5.11.2',
    similarity: 88.4,
    initials: 'LN',
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
}
