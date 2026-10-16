import { Injectable } from '@angular/core';
import { BaseApi, ListParams } from '../api/api-url';
import { AttendanceToday, AttendanceStatusApi, SessionReview } from '../models/catalog';

/** Sesión abierta de HOY (GET /attendance/sessions-today). */
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

/** Asistencias (routers/attendance.py): consulta del día (PLAN §5),
 * marca manual RF-21, rectificación RF-15 y cierre RF-26. */
@Injectable({ providedIn: 'root' })
export class AttendanceApi extends BaseApi {
  /** Registros de HOY (vista v_today_attendance). */
  today(params?: ListParams & {
    course_id?: number;
    room?: string;
    status?: AttendanceStatusApi;
  }) {
    return this.get<AttendanceToday[]>('/attendance/today', params);
  }

  /** Sesiones ABIERTAS de hoy (docente: solo sus grupos). */
  sessionsToday() {
    return this.get<SessionToday[]>('/attendance/sessions-today');
  }

  /** RF-21: marca manual sobre una sesión abierta. */
  manualMark(sessionId: number, body: { student_id: number; status: AttendanceStatusApi }) {
    return this.post<{ record_id: number; student_id: number; status: string; session_id: number }>(
      `/sessions/${sessionId}/manual-mark`,
      body,
    );
  }

  /** RF-15: rectifica el estado de un registro (motivo obligatorio ≥5). */
  rectify(recordId: number, body: { new_status: AttendanceStatusApi; reason: string }) {
    return this.patch<{ record_id: number; status: string }>(
      `/attendance/${recordId}/rectify`,
      body,
    );
  }

  /** R4: sesiones CERRADAS sin marcas (¿cámara caída?) pendientes de resolver. */
  sessionsReview() {
    return this.get<SessionReview[]>('/attendance/sessions-review');
  }

  /** R4: confirma las faltas de la sesión por revisar o la cancela (motivo obligatorio). */
  resolveReview(sessionId: number, body: { action: 'confirmar_faltas' | 'cancelar'; reason?: string }) {
    return this.post<{ session_id: number; status: string; faltas?: number; alertas?: number }>(
      `/sessions/${sessionId}/resolve-review`,
      body,
    );
  }

  /** RF-26: cierre manual de la sesión (admin). */
  closeSession(sessionId: number) {
    return this.post<{ session_id: number; status: string; faltas: number; alertas: number }>(
      `/sessions/${sessionId}/close`,
    );
  }

  /** R5: cancela UNA sesión con motivo (docente: abiertas o por revisar). */
  cancelSession(sessionId: number, body: { reason: string }) {
    return this.post<{ session_id: number; status: string; reason: string }>(
      `/sessions/${sessionId}/cancel`,
      body,
    );
  }

  /** R5: cancela (o pre-cancela en fecha futura) el día completo de un bloque. */
  cancelDay(blockId: number, body: { reason: string; fecha?: string }) {
    return this.post<{ session_id: number; status: string; anticipada?: boolean }>(
      `/blocks/${blockId}/cancel-day`,
      body,
    );
  }

  /** R6: justifica UNA falta creando la justificación del día. */
  justify(recordId: number, body: { reason: string }) {
    return this.patch<{ record_id: number; is_justified: boolean; justification_id: number }>(
      `/attendance/${recordId}/justify`,
      body,
    );
  }
}
