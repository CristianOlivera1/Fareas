import { Injectable } from '@angular/core';
import { BaseApi, Page, ListParams } from '../api/api-url';
import { Block, Course, EnrolledStudent, Group } from '../models/catalog';

/** Carga académica (routers/courses.py): cursos RF-06, grupos, bloques con
 * choques RF-06 y matrículas RF-22. Solo admin escribe (backend re-valida). */
@Injectable({ providedIn: 'root' })
export class CoursesApi extends BaseApi {
  courses(params?: ListParams) {
    return this.get<Page<Course>>('/courses', params);
  }
  createCourse(body: { code: string; name: string }) {
    return this.post<Course>('/courses', body);
  }

  groups(filters?: { course_id?: number; teacher_id?: number; include_inactive?: boolean }) {
    return this.get<Group[]>('/groups', filters);
  }
  courseGroups(courseId: number) {
    return this.get<Group[]>(`/courses/${courseId}/groups`);
  }
  createGroup(
    courseId: number,
    body: { group_code: string; teacher_id: number; room_id: number },
  ) {
    return this.post<Group>(`/courses/${courseId}/groups`, body);
  }
  deactivateGroup(groupId: number) {
    return this.delete<{ message: string }>(`/groups/${groupId}`);
  }

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

  enrolled(groupId: number) {
    return this.get<EnrolledStudent[]>(`/groups/${groupId}/students`);
  }
  enroll(groupId: number, student_id: number) {
    return this.post<{ message: string }>(`/groups/${groupId}/students`, { student_id });
  }
  unenroll(groupId: number, studentId: number) {
    return this.delete<{ message: string }>(`/groups/${groupId}/students/${studentId}`);
  }
}
