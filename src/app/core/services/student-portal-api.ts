import { Injectable } from '@angular/core';

import { BaseApi } from '../api/api-url';
import { ScheduleRow } from '../models/catalog';

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

  justifications() {
    return this.get<MyJustification[]>('/me/justifications');
  }
}
