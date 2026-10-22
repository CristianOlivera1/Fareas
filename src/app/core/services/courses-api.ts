import { Injectable } from '@angular/core';
import { BaseApi, Page, ListParams } from '../api/api-url';
import { Block, Course, EnrolledStudent, Group, ScheduleRow } from '../models/catalog';

@Injectable({ providedIn: 'root' })
export class CoursesApi extends BaseApi {
  courses(params?: ListParams) {
    return this.get<Page<Course>>('/courses', params);
  }
  createCourse(body: { code: string; name: string }) {
    return this.post<Course>('/courses', body);
  }

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
    body: { weekday: number; start_time: string; end_time: string; room_id: number },
  ) {
    return this.post<Block>(`/groups/${groupId}/blocks`, body);
  }
  updateBlock(
    id: number,
    body: { weekday?: number; start_time?: string; end_time?: string; room_id?: number },
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
  transfer(groupId: number, studentId: number, destinoGroupId: number) {
    return this.post<{ message: string }>(
      `/groups/${groupId}/students/${studentId}/transfer`,
      { destino_group_id: destinoGroupId },
    );
  }
}
