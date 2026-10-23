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

@Injectable({ providedIn: 'root' })
export class CalendarApi extends BaseApi {
  holidays(year?: number | null) {
    return this.get<Holiday[]>('/holidays', year ? { year } : undefined);
  }
  createHoliday(body: { holiday_date: string; description: string }) {
    return this.post<HolidayCreated>('/holidays', body);
  }
  createHolidayRange(body: {
    desde: string;
    hasta: string;
    description: string;
    omitir_fines_de_semana?: boolean;
  }) {
    return this.post<HolidayRangeResult>('/holidays/range', body);
  }
  createNationalHolidays(year: number) {
    return this.post<HolidayNationalResult>('/holidays/national', { year });
  }
  deleteHoliday(id: number) {
    return this.delete<{ message: string }>(`/holidays/${id}`);
  }

  justifications(filters?: { student_id?: number; course_id?: number }) {
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
    return this.post<JustificationCreated>('/justifications', body);
  }
  deleteJustification(id: number) {
    return this.delete<{ message: string }>(`/justifications/${id}`);
  }

  settings() {
    return this.get<Settings>('/settings');
  }
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
