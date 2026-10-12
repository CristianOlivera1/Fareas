export interface Room {
  readonly id: number;
  readonly code: string;
  readonly name: string | null;
  readonly building: string | null;
  readonly is_active: boolean;
}

export type DeviceType = 'camara' | 'esp32';

export interface Device {
  readonly id: number;
  readonly room_id: number;
  readonly room_code: string | null;
  readonly device_type: DeviceType;
  readonly device_key: string;
  readonly name: string | null;
  readonly ip_address: string | null;
  readonly rtsp_url?: string | null;
  readonly is_online: boolean;
  readonly last_heartbeat: string | null;
  readonly is_active: boolean;
}

export interface Person {
  readonly id: number;
  readonly role: 'admin' | 'docente' | 'estudiante';
  readonly full_name: string;
  readonly email: string;
  readonly dni: string | null;
  readonly code: string | null;
  readonly whatsapp: string | null;
  readonly semester: number | null;
  readonly is_active: boolean;
  readonly must_change_password: boolean;
  readonly enrolled?: boolean | null;
}

export interface Course {
  readonly id: number;
  readonly code: string;
  readonly name: string;
}

export interface Group {
  readonly id: number;
  readonly course_id: number;
  readonly course_code: string;
  readonly course_name: string;
  readonly group_code: string;
  readonly teacher_id: number;
  readonly teacher_name: string;
  readonly room_id: number;
  readonly room_code: string;
  /** R1: semestre al que pertenece el grupo ('2026-II'). */
  readonly semester_label: string;
  /** R8/R9: cupo del grupo (40 por defecto). */
  readonly capacity: number;
  /** Matrículas activas (no retiradas). */
  readonly enrolled_count: number;
  readonly is_active: boolean;
}

export interface Block {
  readonly id: number;
  readonly group_id: number;
  /** 1=Lunes … 7=Domingo (isoweekday). */
  readonly weekday: number;
  readonly start_time: string; // 'HH:MM:SS'
  readonly end_time: string;
}

export interface EnrolledStudent {
  readonly id: number;
  readonly code: string | null;
  readonly full_name: string;
  readonly email: string;
  readonly semester: number | null;
  readonly enrolled_at: string | null;
  /** R8d: si tiene fecha, la matrícula fue retirada (soft). */
  readonly withdrawn_at: string | null;
  /** RF-04: rostro vigente del alumno. */
  readonly has_face: boolean | null;
}

export interface Holiday {
  readonly id: number;
  readonly holiday_date: string; // 'YYYY-MM-DD'
  readonly description: string;
}

export interface Justification {
  readonly id: number;
  readonly student_id: number;
  readonly student_name: string;
  readonly course_id: number | null;
  readonly course_code: string | null;
  readonly start_date: string;
  readonly end_date: string;
  readonly reason: string;
  readonly document_url: string | null;
  readonly created_by_name: string;
}

export interface Settings {
  readonly semester_label: string;
  /** R1: fechas del semestre vigente (null = sin restricción de fechas). */
  readonly semester_start: string | null;
  readonly semester_end: string | null;
  readonly block_minutes: number;
  readonly late_tolerance_minutes: number;
  /** R2/R3: minutos de apertura anticipada de la ventana de marca. */
  readonly early_open_minutes: number;
  /** R11: días que un docente puede rectificar hacia atrás. */
  readonly rectify_days: number;
  /** R7: mínimo de sesiones para enviar correos de alerta DPI. */
  readonly dpi_min_sessions: number;
  readonly face_match_threshold: number;
  readonly dpi_alert_percent: number;
  readonly dpi_limit_percent: number;
  readonly attendance_hour_start: string;
  readonly attendance_hour_end: string;
  readonly updated_at: string | null;
}

/** Registro de HOY (vista v_today_attendance + attendance.py). */
export type AttendanceStatusApi = 'asistio' | 'tardanza' | 'falta';

/** Registro de HOY (vista v_today_attendance + attendance.py). */
export interface AttendanceToday {
  readonly record_id: number;
  readonly student_id: number;
  readonly student_code: string | null;
  readonly student_name: string;
  readonly course_id: number;
  readonly course_code: string;
  readonly course_name: string;
  readonly group_code: string;
  readonly room_code: string;
  readonly status: AttendanceStatusApi;
  readonly marked_at: string | null;
  readonly method: string;
  readonly similarity: number | null;
}
