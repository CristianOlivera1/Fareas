import { Injectable } from '@angular/core';
import { BaseApi, Page, ListParams } from '../api/api-url';
import { Block, Course, EnrolledStudent, Group } from '../models/catalog';

/** Carga académica (routers/courses.py): cursos RF-06, grupos R9 (semestre +
 * cupo), bloques con choques RF-06 y matrículas R8. Solo admin escribe
 * (el backend re-valida con 403/409). */
@Injectable({ providedIn: 'root' })
export class CoursesApi extends BaseApi {
  // --- Cursos ---
  courses(params?: ListParams) {
    return this.get<Page<Course>>('/courses', params);
  }
  createCourse(body: { code: string; name: string }) {
    return this.post<Course>('/courses', body);
  }

  // --- Grupos (R1: semestre vigente por defecto; R8/R9: cupo) ---
  groups(filters?: {
    course_id?: number;
    teacher_id?: number;
    include_inactive?: boolean;
    semester?: string;
  }) {
    return this.get<Group[]>('/groups', filters);
  }
  courseGroups(courseId: number, semester?: string | null) {
    return this.get<Group[]>(
      `/courses/${courseId}/groups`,
      semester ? { semester } : undefined,
    );
  }
  createGroup(
    courseId: number,
    body: { group_code: string; teacher_id: number; room_id: number; capacity: number },
  ) {
    return this.post<Group>(`/courses/${courseId}/groups`, body);
  }
  deactivateGroup(groupId: number) {
    return this.delete<{ message: string }>(`/groups/${groupId}`);
  }

  // --- Bloques horarios (weekday 1=Lunes … 7=Domingo) ---
  blocks(groupId: number) {
    return this.get<Block[]>(`/groups/${groupId}/blocks`);
  }
  createBlock(groupId: number, body: { weekday: number; start_time: string; end_time: string }) {
    return this.post<Block>(`/groups/${groupId}/blocks`, body);
  }
  updateBlock(id: number, body: { weekday?: number; start_time?: string; end_time?: string }) {
    return this.patch<Block>(`/blocks/${id}`, body);
  }
  deleteBlock(id: number) {
    return this.delete<{ message: string }>(`/blocks/${id}`);
  }

  // --- Matrículas (R8) ---
  enrolled(groupId: number, withFace = true) {
    return this.get<EnrolledStudent[]>(
      `/groups/${groupId}/students`,
      withFace ? { with_face: true } : undefined,
    );
  }
  enroll(groupId: number, studentId: number) {
    return this.post<{ message: string }>(`/groups/${groupId}/students`, {
      student_id: studentId,
    });
  }
  /** R8d: retiro — borra la matrícula si no hay registros; si los hay la
   * marca con withdrawn_at (el historial del alumno en el curso se conserva). */
  unenroll(groupId: number, studentId: number) {
    return this.delete<{ message: string }>(`/groups/${groupId}/students/${studentId}`);
  }
  /** R8e: transferencia entre grupos del MISMO curso. */
  transfer(groupId: number, studentId: number, destinoGroupId: number) {
    return this.post<{ message: string }>(
      `/groups/${groupId}/students/${studentId}/transfer`,
      { destino_group_id: destinoGroupId },
    );
  }
}
