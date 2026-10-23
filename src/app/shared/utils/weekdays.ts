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
