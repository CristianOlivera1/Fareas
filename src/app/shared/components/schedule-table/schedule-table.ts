import {
  ChangeDetectionStrategy,
  Component,
  CUSTOM_ELEMENTS_SCHEMA,
  computed,
  input,
  output,
} from '@angular/core';
import { formatTime, hourValue } from '../../utils/schedule-hours';
import { weekdayLabel } from '../../utils/weekdays';

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

const TONE_COUNT = 8;

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
  protected readonly hourHeightRem = 4;
  readonly canEdit = input(false);
  readonly blockAdd = output<{ weekday: number; hour: number }>();
  readonly blockEdit = output<ScheduleEntry>();
  readonly blockRemove = output<ScheduleEntry>();
  protected readonly formatTime = formatTime;
  protected readonly weekdayLabel = weekdayLabel;

  protected readonly weekdayOptions = computed(() =>
    this.days().map((value) => ({ value, label: weekdayLabel(value) })),
  );

  protected readonly rows = computed(() => this.build(this.entries()));

  protected cellHeight(rowspan: number): number {
    return rowspan * this.hourHeightRem;
  }

  protected courseColorIndex(courseCode: string): number {
    let hash = 0;
    for (const ch of courseCode) hash = (hash * 31 + ch.charCodeAt(0)) % 9973;
    return hash % TONE_COUNT;
  }

  private minutes(value: string): number {
    const [hours, minutes] = formatTime(value).split(':').map(Number);
    return hours * 60 + minutes;
  }

  private build(entries: readonly ScheduleEntry[]): Row[] {
    const weekdays = this.days();
    const scheduleBlocks = entries.map((entry) => {
      const startHour = Math.floor(this.minutes(entry.start_time) / 60);
      const endHour = Math.max(startHour + 1, Math.ceil(this.minutes(entry.end_time) / 60));
      return { entry, startHour, endHour };
    });

    const startHour = scheduleBlocks.length
      ? Math.min(this.hourFrom(), ...scheduleBlocks.map((block) => block.startHour))
      : this.hourFrom();
    const endHour = scheduleBlocks.length
      ? Math.max(this.hourTo(), ...scheduleBlocks.map((block) => block.endHour))
      : this.hourTo();

    const cellsByWeekday = new Map<number, Cell[]>(
      weekdays.map((weekday) => [
        weekday,
        this.buildWeekdayCells(
          scheduleBlocks.filter((block) => block.entry.weekday === weekday),
          startHour,
          endHour,
          weekday,
        ),
      ]),
    );

    const rows: Row[] = [];
    for (let hour = startHour; hour < endHour; hour++) {
      rows.push({
        hour,
        label: `${hourValue(hour)} – ${hourValue(hour + 1)}`,
        cells: weekdays.map((weekday) => cellsByWeekday.get(weekday)?.[hour - startHour] as Cell),
      });
    }
    return rows;
  }

  private buildWeekdayCells(
    scheduleBlocks: { entry: ScheduleEntry; startHour: number; endHour: number }[],
    startHour: number,
    endHour: number,
    weekday: number,
  ): Cell[] {
    const cells: Cell[] = [];
    const coveredHours = new Set<number>();

    for (let hour = startHour; hour < endHour; hour++) {
      if (coveredHours.has(hour)) {
        cells.push({ weekday, entries: [], rowspan: 1, covered: true });
        continue;
      }
      const startingBlocks = scheduleBlocks.filter((block) => block.startHour === hour);
      if (startingBlocks.length === 0) {
        cells.push({ weekday, entries: [], rowspan: 1, covered: false });
        continue;
      }
      const firstBlock = startingBlocks[0];
      const durationHours = firstBlock.endHour - firstBlock.startHour;
      const hasOverlap =
        startingBlocks.length > 1 ||
        scheduleBlocks.some(
          (block) =>
            block !== firstBlock &&
            block.startHour > firstBlock.startHour &&
            block.startHour < firstBlock.endHour,
        );
      if (durationHours > 1 && !hasOverlap) {
        for (let offset = 1; offset < durationHours; offset++) {
          coveredHours.add(hour + offset);
        }
        cells.push({ weekday, entries: [firstBlock.entry], rowspan: durationHours, covered: false });
      } else {
        cells.push({
          weekday,
          entries: startingBlocks.map((block) => block.entry),
          rowspan: 1,
          covered: false,
        });
      }
    }
    return cells;
  }
}
