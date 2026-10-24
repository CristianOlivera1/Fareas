export interface DateRange {
  readonly from: string;
  readonly to: string;
}

export type RangePreset = 'today' | 'week' | 'month' | 'last30' | 'semester' | 'custom';

export function isoDay(date: Date): string {
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${date.getFullYear()}-${month}-${day}`;
}

function shifted(base: Date, days: number): Date {
  const copy = new Date(base);
  copy.setDate(copy.getDate() + days);
  return copy;
}

export function presetRange(
  preset: Exclude<RangePreset, 'custom'>,
  today: Date,
  semester: { start: string | null; end: string | null } | null,
): DateRange {
  const to = isoDay(today);
  if (preset === 'today') return { from: to, to };
  if (preset === 'week') {
    const sinceMonday = (today.getDay() + 6) % 7;
    return { from: isoDay(shifted(today, -sinceMonday)), to };
  }
  if (preset === 'month') {
    return { from: isoDay(new Date(today.getFullYear(), today.getMonth(), 1)), to };
  }
  if (preset === 'semester' && semester?.start) {
    return { from: semester.start, to: semester.end && semester.end < to ? semester.end : to };
  }
  return { from: isoDay(shifted(today, -30)), to };
}
