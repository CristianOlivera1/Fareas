import { Injectable } from '@angular/core';

import { BaseApi } from '../api/api-url';
import { ScheduleRow } from '../models/catalog';

export interface MyBlock {
  readonly weekday: number;
  readonly start_time: string;
  readonly end_time: string;
  readonly room_code: string | null;
}

export interface MyCourse {
  readonly group_id: number;
  readonly course_id: number;
  readonly course_code: string;
  readonly course_name: string;
  readonly cycle: number;
  readonly group_code: string;
  readonly teacher_name: string | null;
  readonly semester_label: string;
  readonly enrolled_at: string | null;
  readonly blocks: MyBlock[];
}

export interface MyJustification {
  readonly id: number;
  readonly course_code: string | null;
  readonly start_date: string;
  readonly end_date: string;
  readonly reason: string;
  readonly document_url: string | null;
  readonly created_by_name: string;
}

@Injectable({ providedIn: 'root' })
export class StudentPortalApi extends BaseApi {
  schedule() {
    return this.get<ScheduleRow[]>('/me/schedule');
  }

  courses() {
    return this.get<MyCourse[]>('/me/courses');
  }

  justifications() {
    return this.get<MyJustification[]>('/me/justifications');
  }
}
