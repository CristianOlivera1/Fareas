import { Injectable } from '@angular/core';
import { BaseApi, ListParams } from '../api/api-url';
import { AttendanceToday, AttendanceStatusApi, SessionReview } from '../models/catalog';

export interface SessionToday {
  readonly session_id: number;
  readonly status: 'abierta' | 'cerrada';
  readonly session_date: string;
  readonly block_id: number;
  readonly weekday: number;
  readonly start_time: string;
  readonly end_time: string;
  readonly group_id: number;
  readonly group_code: string;
  readonly course_id: number;
  readonly course_code: string;
  readonly course_name: string;
  readonly room_id: number;
  readonly room_code: string;
  readonly teacher_id: number;
  readonly teacher_name: string;
}

export interface MyAttendance {
  readonly record_id: number;
  readonly session_id: number;
  readonly session_date: string;
  readonly start_time: string;
  readonly end_time: string;
  readonly course_id: number;
  readonly course_code: string;
  readonly course_name: string;
  readonly group_code: string;
  readonly status: AttendanceStatusApi;
  readonly is_justified: boolean;
  readonly marked_at: string | null;
  readonly method: 'facial' | 'manual';
  readonly correct_reason: string | null;
}

export interface MyDpi {
  readonly course_id: number;
  readonly course_code: string;
  readonly course_name: string;
  readonly sessions_held: number;
  readonly absences: number;
  readonly justified_absences: number;
  readonly lates: number;
  readonly absence_percent: number;
  readonly nivel: 'alerta' | 'limite' | null;
  readonly sesiones_planificadas: number | null;
  readonly faltas_permitidas: number | null;
  readonly faltas_restantes: number | null;
  readonly semester_label: string;
}

@Injectable({ providedIn: 'root' })
export class AttendanceApi extends BaseApi {
  mine(params?: { desde?: string | null; hasta?: string | null }) {
    return this.get<MyAttendance[]>('/attendance/me', { ...params, limit: 500 });
  }

  myDpi() {
    return this.get<MyDpi[]>('/attendance/me/dpi');
  }

  today(params?: ListParams & {
    course_id?: number;
    room?: string;
    status?: AttendanceStatusApi;
  }) {
    return this.get<AttendanceToday[]>('/attendance/today', params);
  }

  sessionsToday() {
    return this.get<SessionToday[]>('/attendance/sessions-today');
  }

  manualMark(sessionId: number, body: { student_id: number; status: AttendanceStatusApi }) {
    return this.post<{ record_id: number; student_id: number; status: string; session_id: number }>(
      `/sessions/${sessionId}/manual-mark`,
      body,
    );
  }

  rectify(recordId: number, body: { new_status: AttendanceStatusApi; reason: string }) {
    return this.patch<{ record_id: number; status: string }>(
      `/attendance/${recordId}/rectify`,
      body,
    );
  }

  sessionsReview() {
    return this.get<SessionReview[]>('/attendance/sessions-review');
  }

  resolveReview(sessionId: number, body: { action: 'confirmar_faltas' | 'cancelar'; reason?: string }) {
    return this.post<{ session_id: number; status: string; faltas?: number; alertas?: number }>(
      `/sessions/${sessionId}/resolve-review`,
      body,
    );
  }

  closeSession(sessionId: number) {
    return this.post<{ session_id: number; status: string; faltas: number; alertas: number }>(
      `/sessions/${sessionId}/close`,
    );
  }

  cancelSession(sessionId: number, body: { reason: string }) {
    return this.post<{ session_id: number; status: string; reason: string }>(
      `/sessions/${sessionId}/cancel`,
      body,
    );
  }

  cancelDay(blockId: number, body: { reason: string; fecha?: string }) {
    return this.post<{ session_id: number; status: string; anticipada?: boolean }>(
      `/blocks/${blockId}/cancel-day`,
      body,
    );
  }

  justify(recordId: number, body: { reason: string }) {
    return this.patch<{ record_id: number; is_justified: boolean; justification_id: number }>(
      `/attendance/${recordId}/justify`,
      body,
    );
  }
}
