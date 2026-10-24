export interface WeekdayOption {
  readonly label: string;
  readonly value: number;
}

export const WEEKDAYS: readonly WeekdayOption[] = [
  { label: 'Lunes', value: 1 },
  { label: 'Martes', value: 2 },
  { label: 'Miércoles', value: 3 },
  { label: 'Jueves', value: 4 },
  { label: 'Viernes', value: 5 },
  { label: 'Sábado', value: 6 },
  { label: 'Domingo', value: 7 },
];

export const LECTURE_WEEKDAYS = WEEKDAYS.slice(0, 5);

export function weekdayLabel(weekday: number): string {
  return WEEKDAYS[weekday - 1]?.label ?? `Día ${weekday}`;
}

const SHORT_WEEKDAYS = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom'];

export function weekdayShort(weekday: number): string {
  return SHORT_WEEKDAYS[weekday - 1] ?? `D${weekday}`;
}

export function blocksLabel(
  blocks: ReadonlyArray<{ weekday: number; start_time: string; end_time: string }>,
): string {
  if (blocks.length === 0) return 'Sin horario';
  return blocks
    .map((block) => `${weekdayShort(block.weekday)} ${block.start_time.slice(0, 5)}–${block.end_time.slice(0, 5)}`)
    .join(' · ');
}
