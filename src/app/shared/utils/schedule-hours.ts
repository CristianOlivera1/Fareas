export const BLOCK_START_HOUR = 7;
export const BLOCK_END_HOUR = 20;
export const BLOCK_MAX_HOURS = 2;

export interface HourOption {
  readonly label: string;
  readonly value: string;
}

export function hourValue(hour: number): string {
  return `${String(hour).padStart(2, '0')}:00`;
}

export function hourNumber(value: string): number {
  return Number(value.slice(0, 2));
}

export function hourOptions(from: number, to: number): HourOption[] {
  const options: HourOption[] = [];
  for (let hour = from; hour <= to; hour += 1) {
    const value = hourValue(hour);
    options.push({ label: value, value });
  }
  return options;
}

export function blockStartOptions(
  from = BLOCK_START_HOUR,
  to = BLOCK_END_HOUR,
): HourOption[] {
  return hourOptions(from, to - 1);
}

export function blockEndOptions(
  startTime: string,
  to = BLOCK_END_HOUR,
  maxHours = BLOCK_MAX_HOURS,
): HourOption[] {
  const start = hourNumber(startTime);
  return hourOptions(start + 1, Math.min(start + maxHours, to));
}

export function nextBlockEnd(
  startTime: string,
  to = BLOCK_END_HOUR,
  maxHours = BLOCK_MAX_HOURS,
): string {
  return hourValue(Math.min(hourNumber(startTime) + maxHours, to));
}

export function validBlockRange(
  startTime: string,
  endTime: string,
  from = BLOCK_START_HOUR,
  to = BLOCK_END_HOUR,
  maxHours = BLOCK_MAX_HOURS,
): boolean {
  if (!startTime || !endTime) return false;
  const start = hourNumber(startTime);
  const end = hourNumber(endTime);
  return start >= from && end <= to && end > start && end - start <= maxHours;
}
