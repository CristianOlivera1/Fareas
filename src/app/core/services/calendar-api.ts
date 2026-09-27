import { Injectable } from '@angular/core';
import { BaseApi } from '../api/api-url';
import { Holiday, Justification, Settings } from '../models/catalog';

/** Calendario (routers/calendar_admin.py): feriados RF-09, justificaciones
 * RF-10 y parámetros globales RF-34. Solo admin escribe (backend re-valida). */
@Injectable({ providedIn: 'root' })
export class CalendarApi extends BaseApi {
  holidays() {
    return this.get<Holiday[]>('/holidays');
  }
  createHoliday(body: { holiday_date: string; description: string }) {
    return this.post<Holiday>('/holidays', body);
  }
  deleteHoliday(id: number) {
    return this.delete<{ message: string }>(`/holidays/${id}`);
  }

  justifications(filters?: { student_id?: number; active_only?: boolean }) {
    return this.get<Justification[]>('/justifications', filters);
  }
  createJustification(body: {
    student_id: number;
    course_id?: number | null;
    start_date: string;
    end_date: string;
    reason: string;
    document_url?: string | null;
  }) {
    return this.post<Justification>('/justifications', body);
  }
  deleteJustification(id: number) {
    return this.delete<{ message: string }>(`/justifications/${id}`);
  }

  settings() {
    return this.get<Settings>('/settings');
  }
  updateSettings(body: Partial<Omit<Settings, 'updated_at' | 'attendance_hour_start' | 'attendance_hour_end'>>) {
    return this.patch<Settings>('/settings', body);
  }
}
