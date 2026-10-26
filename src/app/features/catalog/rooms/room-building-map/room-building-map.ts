import {
  ChangeDetectionStrategy,
  Component,
  CUSTOM_ELEMENTS_SCHEMA,
  computed,
  input,
  output,
} from '@angular/core';
import { Room } from '../../../../core/models/catalog';

interface SceneWindow {
  readonly x: number;
  readonly y: number;
  readonly w: number;
  readonly h: number;
  readonly shine: string;
}

interface SkewWindow extends SceneWindow {
  readonly skew: number;
}

interface StairFlight {
  readonly y: number;
  readonly risers: readonly number[];
}

interface Bush {
  readonly x: number;
  readonly y: number;
  readonly scale: number;
}

interface FloorSpec {
  readonly level: number;
  readonly label: string;
  readonly color: string;
  readonly topLeft: number;
  readonly topRight: number;
  readonly bottomLeft: number;
  readonly bottomRight: number;
}

interface RoomPoint {
  readonly room: Room;
  readonly x: number;
  readonly y: number;
  readonly width: number;
  readonly fontSize: number;
  readonly connector: boolean;
}

interface FloorMap {
  readonly level: number;
  readonly label: string;
  readonly color: string;
  readonly parapet: string;
  readonly topLine: string;
  readonly shade: string;
  readonly rooms: readonly RoomPoint[];
}

/** Tramos verticales de la fachada principal (mismo trazado que la ilustración original). */
const FACADE_LEFT = 805;
const FACADE_RIGHT = 1355;
const MAX_MARKERS_PER_FLOOR = 4;

/** Centros de los cuatro tramos de fachada; ningún rótulo cae sobre una columna. */
const FACADE_SLOTS = [849, 970, 1123, 1284] as const;

/**
 * Aula que la ilustración original dibuja en el tramo del conector (torre de escaleras),
 * arriba de la ventana del tercer piso. El resto de aulas del piso van a la fachada.
 */
const CONNECTOR_ROOM_NUMBER = '303';
const CONNECTOR_SLOT = { x: 667, y: 574 } as const;

const FLOORS: readonly FloorSpec[] = [
  {
    level: 4,
    label: 'Salones 400',
    color: '#1e7be0',
    topLeft: 484,
    topRight: 430,
    bottomLeft: 526,
    bottomRight: 498,
  },
  {
    level: 3,
    label: 'Salones 300',
    color: '#2f8052',
    topLeft: 562,
    topRight: 536,
    bottomLeft: 622,
    bottomRight: 598,
  },
  {
    level: 2,
    label: 'Salones 200',
    color: '#d9820a',
    topLeft: 657,
    topRight: 645,
    bottomLeft: 715,
    bottomRight: 705,
  },
  {
    level: 1,
    label: 'Salones 100',
    color: '#7a3fc0',
    topLeft: 748,
    topRight: 748,
    bottomLeft: 802,
    bottomRight: 802,
  },
];

const FACADE_BAYS: readonly (readonly [number, number])[] = [
  [808, 893],
  [907, 1033],
  [1050, 1197],
  [1213, 1355],
];

const WINDOW_OFFSETS = [0.12, 0.56] as const;

function lerp(from: number, to: number, amount: number): number {
  return from + (to - from) * amount;
}

function facadeProgress(x: number): number {
  return (x - FACADE_LEFT) / (FACADE_RIGHT - FACADE_LEFT);
}

function floorTop(floor: FloorSpec, x: number): number {
  return lerp(floor.topLeft, floor.topRight, facadeProgress(x));
}

function floorBottom(floor: FloorSpec, x: number): number {
  return lerp(floor.bottomLeft, floor.bottomRight, facadeProgress(x));
}

function sceneWindow(x: number, y: number, w: number, h: number): SceneWindow {
  return {
    x,
    y,
    w,
    h,
    shine: `${x + 2},${y + 2} ${x + w * 0.55},${y + 2} ${x + 2},${y + h * 0.6}`,
  };
}

function buildFacadeWindows(): { glass: string[]; strips: string[] } {
  const glass: string[] = [];
  const strips: string[] = [];

  for (const floor of FLOORS) {
    for (const [start, end] of FACADE_BAYS) {
      const width = end - start;

      for (const offset of WINDOW_OFFSETS) {
        const from = start + width * offset;
        const to = from + width * 0.32;
        glass.push(
          `${from},${floorTop(floor, from) - 26} ${to},${floorTop(floor, to) - 26} ` +
            `${to},${floorTop(floor, to)} ${from},${floorTop(floor, from)}`,
        );
      }

      strips.push(
        `${start},${floorTop(floor, start) - 36} ${end},${floorTop(floor, end) - 36} ` +
          `${end},${floorTop(floor, end) - 30} ${start},${floorTop(floor, start) - 30}`,
      );
    }
  }

  return { glass, strips };
}

@Component({
  selector: 'app-room-building-map',
  templateUrl: './room-building-map.html',
  styleUrl: './room-building-map.css',
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class RoomBuildingMap {
  readonly rooms = input<Room[]>([]);
  readonly selectedRoom = input<Room | null>(null);
  readonly loading = input(false);
  readonly selected = output<Room | null>();
  readonly edit = output<Room>();

  private readonly facadeWindows = buildFacadeWindows();

  /** Orden natural por código: la API devuelve las aulas de la más nueva a la más antigua. */
  private readonly sortedRooms = computed(() =>
    [...this.rooms()].sort((a, b) => a.code.localeCompare(b.code, 'es', { numeric: true })),
  );

  readonly facadeGlass = this.facadeWindows.glass;
  readonly facadeStrips = this.facadeWindows.strips;

  readonly leftMullions = Array.from({ length: 4 }, (_, index) => 68 + (index + 1) * 20);
  readonly leftGlassRows = Array.from({ length: 7 }, (_, index) => 430 + (index + 1) * 29);

  readonly oliveWindows = (
    [
      [182, 446],
      [222, 446],
      [182, 558],
      [222, 558],
    ] as const
  ).map(([x, y]) => sceneWindow(x, y, 30, 70));

  readonly roundStripes = Array.from({ length: 14 }, (_, index) => 330 + index * 20);

  readonly roundWindows: readonly SkewWindow[] = (
    [
      { x: 352, y: 514, skew: 9, h: 40 },
      { x: 440, y: 518, skew: 0, h: 40 },
      { x: 518, y: 514, skew: -10, h: 40 },
      { x: 352, y: 612, skew: 9, h: 38 },
      { x: 440, y: 616, skew: 0, h: 38 },
      { x: 518, y: 612, skew: -10, h: 38 },
    ] as const
  ).map(({ x, y, skew, h }) => ({ ...sceneWindow(x, y, 28, h), skew }));

  readonly doorMullions = Array.from({ length: 6 }, (_, index) => 356 + index * 30.6);

  readonly stairs: readonly StairFlight[] = [492, 584, 678].map((y) => ({
    y,
    risers: Array.from({ length: 9 }, (_, index) => 716 + index * 9.4),
  }));

  readonly facadeColumns: readonly { x: number; width: number; top: number; height: number }[] = [
    { x: 893, width: 14 },
    { x: 1033, width: 17 },
    { x: 1197, width: 16 },
  ].map((column) => {
    const top = 447 - (column.x - 803) * 0.1678 - 4;
    return { ...column, top, height: 806 - top };
  });

  readonly bushes: readonly Bush[] = [
    { x: 290, y: 790, scale: 1 },
    { x: 468, y: 818, scale: 1.1 },
    { x: 610, y: 790, scale: 0.8 },
    { x: 926, y: 818, scale: 1.1 },
    { x: 1140, y: 828, scale: 1 },
    { x: 1318, y: 826, scale: 0.9 },
    { x: 1458, y: 818, scale: 1.1 },
    { x: 215, y: 850, scale: 1 },
    { x: 80, y: 826, scale: 0.8 },
  ];

  readonly railings = [
    { y: 440, height: 42, posts: 5 },
    { y: 536, height: 44, posts: 5 },
    { y: 645, height: 31, posts: 4 },
  ].map((railing) => ({
    ...railing,
    posts: Array.from({ length: railing.posts }, (_, index) => 1400 + index * 5.5),
  }));

  readonly floors = computed<FloorMap[]>(() =>
    FLOORS.map((floor) => {
      const floorRooms = this.sortedRooms().filter((room) => this.floorFor(room) === floor.level);
      const connectorRooms = floorRooms.filter((room) => this.isConnectorRoom(room));
      const facadeRooms = floorRooms.filter((room) => !this.isConnectorRoom(room));

      return {
        level: floor.level,
        label: floor.label,
        color: floor.color,
        parapet:
          `${FACADE_LEFT},${floor.topLeft} ${FACADE_RIGHT},${floor.topRight} ` +
          `${FACADE_RIGHT},${floor.bottomRight} ${FACADE_LEFT},${floor.bottomLeft}`,
        topLine: `${FACADE_LEFT},${floor.topLeft} ${FACADE_RIGHT},${floor.topRight}`,
        shade:
          `${FACADE_LEFT},${floor.bottomLeft} ${FACADE_RIGHT},${floor.bottomRight} ` +
          `${FACADE_RIGHT},${floor.bottomRight + 14} ${FACADE_LEFT},${floor.bottomLeft + 14}`,
        rooms: [
          ...this.layoutRooms(floor, facadeRooms.slice(0, MAX_MARKERS_PER_FLOOR)),
          ...connectorRooms.map((room) => this.connectorPoint(room)),
        ],
      };
    }),
  );

  readonly selectedFloor = computed(() => {
    const room = this.selectedRoom();
    return room ? this.floorFor(room) : null;
  });

  /** Aulas que no se dibujan en el plano (sin piso en el código o sin tramo disponible). */
  readonly outsideRooms = computed(() => {
    const shown = new Set(
      this.floors().flatMap((floor) => floor.rooms.map((point) => point.room.id)),
    );
    return this.sortedRooms().filter((room) => !shown.has(room.id));
  });

  toggleRoom(room: Room): void {
    this.selected.emit(this.selectedRoom()?.id === room.id ? null : room);
  }

  requestEdit(room: Room, event: Event): void {
    event.stopPropagation();
    this.edit.emit(room);
  }

  handleRoomKeydown(event: KeyboardEvent, room: Room): void {
    if (event.key !== 'Enter' && event.key !== ' ') return;
    event.preventDefault();
    this.toggleRoom(room);
  }

  floorLabelFor(room: Room): string {
    const level = this.floorFor(room);
    return level === null ? 'sin piso en el código' : `${level}° piso`;
  }

  private layoutRooms(floor: FloorSpec, rooms: readonly Room[]): RoomPoint[] {
    const count = rooms.length;
    const first = FACADE_SLOTS[0];
    const last = FACADE_SLOTS[FACADE_SLOTS.length - 1];
    const slots = rooms.map((_, index) => {
      // Un aula sola se ubica en el primer tramo de la fachada, sobre el primer salón del piso inferior.
      if (count === 1) return FACADE_SLOTS[0];

      const ideal = first + ((last - first) * index) / (count - 1);
      return FACADE_SLOTS.reduce((closest, slot) =>
        Math.abs(slot - ideal) < Math.abs(closest - ideal) ? slot : closest,
      );
    });

    return rooms.map((room, index) => {
      const x = slots[index];
      return {
        room,
        x,
        y: (floorTop(floor, x) + floorBottom(floor, x)) / 2,
        ...this.metrics(room),
        connector: false,
      };
    });
  }

  private connectorPoint(room: Room): RoomPoint {
    return {
      room,
      x: CONNECTOR_SLOT.x,
      y: CONNECTOR_SLOT.y,
      ...this.metrics(room),
      connector: true,
    };
  }

  private metrics(room: Room): { width: number; fontSize: number } {
    const fontSize =
      room.code.length <= 3 ? 21 : room.code.length <= 4 ? 18 : room.code.length <= 6 ? 15 : 13;

    return { fontSize, width: Math.max(64, room.code.length * fontSize * 0.6 + 26) };
  }

  private isConnectorRoom(room: Room): boolean {
    return this.floorFor(room) === 3 && this.roomNumber(room) === CONNECTOR_ROOM_NUMBER;
  }

  private roomNumber(room: Room): string | null {
    return room.code.match(/(\d{3})\s*$/)?.[1] ?? null;
  }

  private floorFor(room: Room): number | null {
    const match = room.code.match(/(?:^|\D)([1-4])\d{2}(?:\D|$)/);
    return match ? Number(match[1]) : null;
  }
}
