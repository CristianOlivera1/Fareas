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
  readonly avatar_url?: string | null;
}

export interface Course {
  readonly id: number;
  readonly code: string;
  readonly name: string;
  readonly cycle: number;
}

export interface FullCourse {
  readonly course_id: number;
  readonly code: string;
  readonly name: string;
  readonly cycle: number;
  readonly groups: number;
  readonly enrolled: number;
  readonly capacity: number;
}

export interface Group {
  readonly id: number;
  readonly course_id: number;
  readonly course_code: string;
  readonly course_name: string;
  readonly group_code: string;
  readonly teacher_id: number | null;
  readonly teacher_name: string | null;
  readonly semester_label: string;
  readonly cycle: number;
  readonly capacity: number;
  readonly enrolled_count: number;
  readonly is_active: boolean;
}

export interface ScheduleRow {
  readonly id: number;
  readonly group_id: number;
  readonly course_id: number;
  readonly course_code: string;
  readonly course_name: string;
  readonly group_code: string;
  readonly teacher_id: number | null;
  readonly teacher_name: string | null;
  readonly room_id: number | null;
  readonly room_code: string | null;
  readonly semester_label: string;
  readonly cycle: number;
  readonly weekday: number;
  readonly start_time: string;
  readonly end_time: string;
}

export interface Block {
  readonly id: number;
  readonly group_id: number;
  readonly room_id: number | null;
  readonly room_code: string | null;
  readonly teacher_id: number | null;
  readonly teacher_name: string | null;
  readonly weekday: number;
  readonly start_time: string;
  readonly end_time: string;
}

export interface EnrolledStudent {
  readonly id: number;
  readonly code: string | null;
  readonly full_name: string;
  readonly email: string;
  readonly semester: number | null;
  readonly enrolled_at: string | null;
  readonly withdrawn_at: string | null;
  readonly has_face: boolean | null;
  readonly avatar_url?: string | null;
}

export interface Holiday {
  readonly id: number;
  readonly holiday_date: string;
  readonly description: string;
}

export interface HolidayCreated extends Holiday {
  readonly sesiones_canceladas: number;
}

export interface HolidayRangeResult {
  readonly creados: number;
  readonly omitidos: number;
  readonly sesiones_canceladas: number;
}

export interface HolidayNationalResult {
  readonly anio: number;
  readonly creados: number;
  readonly omitidos: number;
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
  readonly created_by: number;
  readonly created_by_name: string;
}

export interface JustificationCreated {
  readonly id: number;
  readonly student_id: number;
  readonly course_id: number | null;
  readonly start_date: string;
  readonly end_date: string;
  readonly faltas_afectadas: number;
  readonly message: string;
}

export interface Settings {
  readonly semester_label: string;
  readonly semester_start: string | null;
  readonly semester_end: string | null;
  readonly enrollment_start?: string | null;
  readonly enrollment_end?: string | null;
  readonly block_minutes: number;
  readonly late_tolerance_minutes: number;
  readonly early_open_minutes: number;
  readonly rectify_days: number;
  readonly dpi_min_sessions: number;
  readonly face_match_threshold: number;
  readonly dpi_alert_percent: number;
  readonly dpi_limit_percent: number;
  readonly attendance_hour_start: string;
  readonly attendance_hour_end: string;
  readonly updated_at: string | null;
}

export type AttendanceStatusApi = 'asistio' | 'tardanza' | 'falta';

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
  readonly is_justified: boolean;
  readonly session_id: number;
}

export interface SessionReview {
  readonly session_id: number;
  readonly session_date: string;
  readonly closed_at: string | null;
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
