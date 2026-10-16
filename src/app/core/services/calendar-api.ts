import { Injectable } from '@angular/core';
import { BaseApi } from '../api/api-url';
import {
  Holiday,
  HolidayCreated,
  HolidayNationalResult,
  HolidayRangeResult,
  Justification,
  JustificationCreated,
  Settings,
} from '../models/catalog';

/** Calendario (routers/calendar_admin.py): feriados RF-09/R12, justificaciones
 * RF-10/R6 y parámetros globales RF-34. Solo admin escribe (backend re-valida). */
@Injectable({ providedIn: 'root' })
export class CalendarApi extends BaseApi {
  holidays(year?: number | null) {
    return this.get<Holiday[]>('/holidays', year ? { year } : undefined);
  }
  /** R12: registrar la fecha CANCELA las sesiones de ese día (devuelve cuántas). */
  createHoliday(body: { holiday_date: string; description: string }) {
    return this.post<HolidayCreated>('/holidays', body);
  }
  /** R12: paro/feriado por rango (omite fines de semana por defecto). */
  createHolidayRange(body: {
    desde: string;
    hasta: string;
    description: string;
    omitir_fines_de_semana?: boolean;
  }) {
    return this.post<HolidayRangeResult>('/holidays/range', body);
  }
  /** R12: genera los feriados NACIONALES del año (fijos + Semana Santa). */
  createNationalHolidays(year: number) {
    return this.post<HolidayNationalResult>('/holidays/national', { year });
  }
  deleteHoliday(id: number) {
    return this.delete<{ message: string }>(`/holidays/${id}`);
  }

  justifications(filters?: { student_id?: number; course_id?: number }) {
    return this.get<Justification[]>('/justifications', filters);
  }
  /** R6: el alta informa faltas_afectadas; el docente DEBE elegir curso. */
  createJustification(body: {
    student_id: number;
    course_id?: number | null;
    start_date: string;
    end_date: string;
    reason: string;
    document_url?: string | null;
  }) {
    return this.post<JustificationCreated>('/justifications', body);
  }
  /** R6: eliminar revierte las faltas que había justificado. */
  deleteJustification(id: number) {
    return this.delete<{ message: string }>(`/justifications/${id}`);
  }

  settings() {
    return this.get<Settings>('/settings');
  }
  /** R1: etiquetas de semestre que ya tienen grupos (selectores del panel). */
  semesters() {
    return this.get<string[]>('/settings/semesters');
  }
  updateSettings(
    body: Partial<Omit<Settings, 'updated_at' | 'attendance_hour_start' | 'attendance_hour_end'>> & {
      attendance_hour_start?: string;
      attendance_hour_end?: string;
    },
  ) {
    return this.patch<Settings>('/settings', body);
  }
}
