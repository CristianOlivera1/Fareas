import {
  ChangeDetectionStrategy,
  Component,
  CUSTOM_ELEMENTS_SCHEMA,
  computed,
  input,
  output,
} from '@angular/core';

export interface ScheduleEntry {
  readonly id: number | string;
  readonly weekday: number;
  readonly start_time: string;
  readonly end_time: string;
  readonly course_code: string;
  readonly course_name?: string | null;
  readonly group_code?: string | null;
  readonly room_code?: string | null;
  readonly teacher_name?: string | null;
}

interface Cell {
  readonly weekday: number;
  readonly entries: ScheduleEntry[];
  readonly rowspan: number;
  readonly covered: boolean;
}

interface Row {
  readonly hour: number;
  readonly label: string;
  readonly cells: Cell[];
}

const DIAS = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo'];

const TONOS = 8;

@Component({
  selector: 'app-schedule-table',
  imports: [],
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  templateUrl: './schedule-table.html',
  styleUrl: './schedule-table.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { class: 'block' },
})
export class ScheduleTable {
  readonly entries = input<readonly ScheduleEntry[]>([]);
  readonly days = input<readonly number[]>([1, 2, 3, 4, 5]);
  readonly hourFrom = input(7);
  readonly hourTo = input(20);
  protected readonly horaRem = 4;
  readonly canEdit = input(false);
  readonly blockAdd = output<{ weekday: number; hour: number }>();
  readonly blockRemove = output<ScheduleEntry>();

  protected readonly dayLabels = computed(() =>
    this.days().map((value) => ({ value, label: DIAS[value - 1] ?? `Día ${value}` })),
  );

  protected readonly rows = computed(() => this.build(this.entries()));

  protected dayLabel(weekday: number): string {
    return DIAS[weekday - 1] ?? `Día ${weekday}`;
  }

  protected altoCelda(rowspan: number): number {
    return rowspan * this.horaRem;
  }

  protected hhmm(value: string): string {
    return value.slice(0, 5);
  }

  protected tono(courseCode: string): number {
    let hash = 0;
    for (const ch of courseCode) hash = (hash * 31 + ch.charCodeAt(0)) % 9973;
    return hash % TONOS;
  }

  private minutes(value: string): number {
    const [h, m] = this.hhmm(value).split(':').map(Number);
    return h * 60 + m;
  }

  private hora(hour: number): string {
    return `${String(hour).padStart(2, '0')}:00`;
  }

  private build(entries: readonly ScheduleEntry[]): Row[] {
    const dias = this.days();
    const bloques = entries.map((e) => {
      const desde = Math.floor(this.minutes(e.start_time) / 60);
      const hasta = Math.max(desde + 1, Math.ceil(this.minutes(e.end_time) / 60));
      return { e, desde, hasta };
    });

    const inicio = bloques.length ? Math.min(this.hourFrom(), ...bloques.map((b) => b.desde)) : this.hourFrom();
    const fin = bloques.length ? Math.max(this.hourTo(), ...bloques.map((b) => b.hasta)) : this.hourTo();

    const porDia = new Map<number, Cell[]>(
      dias.map((d) => [d, this.cellsDelDia(bloques.filter((b) => b.e.weekday === d), inicio, fin, d)]),
    );

    const rows: Row[] = [];
    for (let hour = inicio; hour < fin; hour++) {
      rows.push({
        hour,
        label: `${this.hora(hour)} – ${this.hora(hour + 1)}`,
        cells: dias.map((d) => porDia.get(d)?.[hour - inicio] as Cell),
      });
    }
    return rows;
  }

  private cellsDelDia(
    bloques: { e: ScheduleEntry; desde: number; hasta: number }[],
    inicio: number,
    fin: number,
    weekday: number,
  ): Cell[] {
    const celdas: Cell[] = [];
    const pintadas = new Set<number>();

    for (let hour = inicio; hour < fin; hour++) {
      if (pintadas.has(hour)) {
        celdas.push({ weekday, entries: [], rowspan: 1, covered: true });
        continue;
      }
      const aqui = bloques.filter((b) => b.desde === hour);
      if (aqui.length === 0) {
        celdas.push({ weekday, entries: [], rowspan: 1, covered: false });
        continue;
      }
      const primero = aqui[0];
      const span = primero.hasta - primero.desde;
      const solapado =
        aqui.length > 1 || bloques.some((b) => b !== primero && b.desde > primero.desde && b.desde < primero.hasta);
      if (span > 1 && !solapado) {
        for (let k = 1; k < span; k++) pintadas.add(hour + k);
        celdas.push({ weekday, entries: [primero.e], rowspan: span, covered: false });
      } else {
        celdas.push({ weekday, entries: aqui.map((b) => b.e), rowspan: 1, covered: false });
      }
    }
    return celdas;
  }
}
