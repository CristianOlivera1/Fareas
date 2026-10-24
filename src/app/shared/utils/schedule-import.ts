import type { ScheduleImportRow } from '../../core/models/imports';
import { timeToMinutes } from './schedule-hours';

export interface ScheduleImportGroup {
  readonly code: string;
  readonly name: string;
  readonly rows: ScheduleImportRow[];
}

export function groupScheduleImportRows(
  rows: readonly ScheduleImportRow[],
): ScheduleImportGroup[] {
  const sortedRows = [...rows].sort(
    (first, second) =>
      first.course_code.localeCompare(second.course_code) ||
      first.group_code.localeCompare(second.group_code) ||
      first.weekday - second.weekday ||
      first.start_time.localeCompare(second.start_time),
  );
  const groupedRows = new Map<string, ScheduleImportRow[]>();

  for (const row of sortedRows) {
    const courseCode = row.course_code.trim().toUpperCase() || 'SIN CURSO';
    const courseRows = groupedRows.get(courseCode) ?? [];
    courseRows.push(row);
    groupedRows.set(courseCode, courseRows);
  }

  return [...groupedRows.entries()].map(([code, courseRows]) => ({
    code,
    name: courseRows.find((row) => row.course_name.trim())?.course_name.trim() ?? 'Curso sin nombre',
    rows: courseRows,
  }));
}

export function scheduleImportRowIssues(
  row: ScheduleImportRow,
  hourFrom: string,
  hourTo: string,
): string[] {
  const issues: string[] = [];
  const courseCode = row.course_code.trim();
  const groupCode = row.group_code.trim();

  if (courseCode.length < 3 || courseCode.length > 20) {
    issues.push('Código de curso de 3 a 20 caracteres');
  }
  if (groupCode.length < 1 || groupCode.length > 5) {
    issues.push('Grupo de 1 a 5 caracteres');
  }
  if (!Number.isInteger(row.weekday) || row.weekday < 1 || row.weekday > 5) {
    issues.push('Día de lunes a viernes');
  }

  const startMinutes = timeToMinutes(row.start_time);
  const endMinutes = timeToMinutes(row.end_time);
  const earliestMinutes = timeToMinutes(hourFrom);
  const latestMinutes = timeToMinutes(hourTo);

  if (startMinutes === null || endMinutes === null) {
    issues.push('Hora de inicio y fin válidas');
  } else {
    if (startMinutes >= endMinutes) {
      issues.push('La hora de inicio debe ser menor que la de fin');
    }
    const duration = endMinutes - startMinutes;
    if (duration > 0 && duration !== 60 && duration !== 120) {
      issues.push('El bloque debe durar exactamente 1 o 2 horas');
    }
    if (earliestMinutes !== null && startMinutes < earliestMinutes) {
      issues.push(`La clase empieza antes de ${hourFrom}`);
    }
    if (latestMinutes !== null && endMinutes > latestMinutes) {
      issues.push(`La clase termina después de ${hourTo}`);
    }
  }

  return issues;
}
