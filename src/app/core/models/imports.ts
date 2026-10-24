export interface CourseSuggestion {
  readonly id: number;
  readonly code: string;
  readonly name: string;
  readonly cycle: number;
  readonly score: number;
  readonly motivo: string;
}

export interface ScheduleImportBlock {
  readonly course_code: string | null;
  readonly course_name: string | null;
  readonly group_code: string | null;
  readonly teacher_name: string | null;
  readonly room_code: string | null;
  readonly teacher_id: number | null;
  readonly room_id: number | null;
  readonly curso_sugerido: CourseSuggestion | null;
  readonly weekday: number;
  readonly start_time: string;
  readonly end_time: string;
  readonly confiable: boolean;
  readonly nota: string | null;
  readonly linea: string;
  readonly pagina: number;
  readonly confianza: number;
}

export interface ScheduleImportPreview {
  readonly tipo: string;
  readonly paginas: number;
  readonly total: number;
  readonly confiables: number;
  readonly ambiguousos: number;
  readonly bloques: ScheduleImportBlock[];
}

export interface ScheduleImportRow {
  readonly key: string;
  course_code: string;
  course_name: string;
  group_code: string;
  weekday: number;
  start_time: string;
  end_time: string;
  teacher_id: number | null;
  room_id: number | null;
  teacher_name: string | null;
  room_code: string | null;
  course_suggestion: CourseSuggestion | null;
  suggestion_dismissed: boolean;
  confiable: boolean;
  nota: string | null;
  linea: string;
  pagina: number;
}

export interface ScheduleImportBlockIn {
  readonly course_code: string;
  readonly course_name: string | null;
  readonly group_code: string;
  readonly weekday: number;
  readonly start_time: string;
  readonly end_time: string;
  readonly teacher_id: number | null;
  readonly room_id: number | null;
}

export interface ScheduleImportConfirmIn {
  readonly teacher_id: number | null;
  readonly room_id: number | null;
  readonly cycle: number;
  readonly semester_label: string;
  readonly bloques: ScheduleImportBlockIn[];
}

export interface ScheduleImportResult {
  readonly cursos_creados: string[];
  readonly grupos_creados: string[];
  readonly bloques_creados: number;
  readonly omitidos: number;
  readonly total_bloques: number;
}

export interface StudentImportRow {
  readonly fila: number;
  readonly code: string | null;
  readonly dni: string | null;
  readonly full_name: string | null;
  readonly email: string | null;
  readonly email_generado: boolean;
  readonly semester: number | null;
  readonly whatsapp: string | null;
  readonly confiable: boolean;
  readonly duplicado: boolean;
  readonly errores: string[];
  readonly nota: string | null;
  readonly linea: string;
  readonly pagina: number;
}

export interface StudentImportPreview {
  readonly tipo: string;
  readonly paginas: number;
  readonly total: number;
  readonly listos: number;
  readonly con_error: number;
  readonly alumnos: StudentImportRow[];
}

export interface StudentImportEditableRow {
  readonly key: string;
  fila: number;
  code: string;
  dni: string;
  full_name: string;
  email: string;
  email_generado: boolean;
  semester: number | null;
  whatsapp: string;
  duplicado: boolean;
  errores: string[];
  nota: string | null;
  linea: string;
  pagina: number;
}

export interface StudentImportRowIn {
  readonly fila: number;
  readonly code: string;
  readonly dni: string;
  readonly full_name: string;
  readonly email: string | null;
  readonly semester: number | null;
  readonly whatsapp: string | null;
}

export interface StudentImportConfirmIn {
  readonly alumnos: StudentImportRowIn[];
  readonly group_id: number | null;
}

export interface StudentImportError {
  readonly fila: number;
  readonly code: string | null;
  readonly motivo: string;
}

export interface StudentImportResult {
  readonly creados: number;
  readonly omitidos: number;
  readonly matriculados: number;
  readonly total: number;
  readonly errores: StudentImportError[];
}

export interface CurriculumExistingCourse {
  readonly id: number;
  readonly name: string;
  readonly cycle: number;
}

export interface CurriculumPreviewRow {
  readonly fila: number;
  readonly code: string;
  readonly name: string;
  readonly cycle: number | null;
  readonly confiable: boolean;
  readonly nota: string | null;
  readonly linea: string;
  readonly pagina: number;
  readonly ya_existe: boolean;
  readonly existente: CurriculumExistingCourse | null;
}

export interface CurriculumPreview {
  readonly tipo: string;
  readonly paginas: number;
  readonly total: number;
  readonly listos: number;
  readonly por_revisar: number;
  readonly ya_existentes: number;
  readonly ciclos: number[];
  readonly cursos: CurriculumPreviewRow[];
}

export interface CurriculumEditableRow {
  readonly key: string;
  code: string;
  name: string;
  cycle: number | null;
  confiable: boolean;
  nota: string | null;
  linea: string;
  ya_existe: boolean;
  existente: CurriculumExistingCourse | null;
}

export interface CurriculumConfirmIn {
  readonly cursos: Array<{ code: string; name: string; cycle: number }>;
}

export interface CurriculumResult {
  readonly creados: number;
  readonly omitidos: number;
  readonly codigos_creados: string[];
  readonly codigos_omitidos: string[];
  readonly total: number;
}
