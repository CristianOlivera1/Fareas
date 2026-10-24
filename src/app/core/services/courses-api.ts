import { Injectable } from '@angular/core';
import { apiUrl, BaseApi, Page, ListParams } from '../api/api-url';
import { Block, Course, EnrolledStudent, Group, ScheduleRow } from '../models/catalog';
import {
  CurriculumConfirmIn,
  CurriculumPreview,
  CurriculumResult,
  ScheduleImportConfirmIn,
  ScheduleImportPreview,
  ScheduleImportResult,
} from '../models/imports';

@Injectable({ providedIn: 'root' })
export class CoursesApi extends BaseApi {
  courses(params?: ListParams & { cycle?: number }) {
    return this.get<Page<Course>>('/courses', params);
  }
  createCourse(body: { code: string; name: string; cycle: number }) {
    return this.post<Course>('/courses', body);
  }
  updateCourse(id: number, body: { code?: string; name?: string; cycle?: number }) {
    return this.patch<Course>(`/courses/${id}`, body);
  }
  deleteCourse(id: number) {
    return this.delete<{ message: string }>(`/courses/${id}`);
  }

  groups(filters?: {
    course_id?: number;
    teacher_id?: number;
    include_inactive?: boolean;
    semester?: string;
    cycle?: number;
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
    body: { group_code: string; teacher_id: number; capacity: number },
  ) {
    return this.post<Group>(`/courses/${courseId}/groups`, body);
  }
  deactivateGroup(groupId: number) {
    return this.delete<{ message: string }>(`/groups/${groupId}`);
  }
  activateGroup(groupId: number) {
    return this.post<{ message: string }>(`/groups/${groupId}/activate`);
  }

  schedule(filters: {
    semester?: string;
    cycle?: number;
    course_id?: number;
    teacher_id?: number;
    room_id?: number;
    include_inactive?: boolean;
  }) {
    return this.get<ScheduleRow[]>('/schedule', filters);
  }

  blocks(groupId: number) {
    return this.get<Block[]>(`/groups/${groupId}/blocks`);
  }
  createBlock(
    groupId: number,
    body: {
      weekday: number;
      start_time: string;
      end_time: string;
      room_id: number | null;
      teacher_id: number | null;
    },
  ) {
    return this.post<Block>(`/groups/${groupId}/blocks`, body);
  }
  updateBlock(
    id: number,
    body: {
      weekday?: number;
      start_time?: string;
      end_time?: string;
      room_id?: number | null;
      teacher_id?: number | null;
    },
  ) {
    return this.patch<Block>(`/blocks/${id}`, body);
  }
  deleteBlock(id: number) {
    return this.delete<{ message: string }>(`/blocks/${id}`);
  }

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
  unenroll(groupId: number, studentId: number) {
    return this.delete<{ message: string }>(`/groups/${groupId}/students/${studentId}`);
  }
  transfer(groupId: number, studentId: number, destinationGroupId: number) {
    return this.post<{ message: string }>(
      `/groups/${groupId}/students/${studentId}/transfer`,
      { destino_group_id: destinationGroupId },
    );
  }

  importSchedule(file: File) {
    const body = new FormData();
    body.append('file', file);
    return this.http.post<ScheduleImportPreview>(apiUrl('/courses/import-pdf'), body);
  }
  confirmScheduleImport(body: ScheduleImportConfirmIn) {
    return this.post<ScheduleImportResult>('/courses/import-pdf/confirm', body);
  }

  importCurriculum(file: File, defaultCycle: number | null) {
    const body = new FormData();
    body.append('file', file);
    if (defaultCycle !== null) body.append('default_cycle', String(defaultCycle));
    return this.http.post<CurriculumPreview>(apiUrl('/courses/import-curriculum'), body);
  }
  confirmCurriculum(body: CurriculumConfirmIn) {
    return this.post<CurriculumResult>('/courses/import-curriculum/confirm', body);
  }
}
