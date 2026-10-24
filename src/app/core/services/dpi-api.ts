import { Injectable } from '@angular/core';

import { BaseApi } from '../api/api-url';

export type DpiLevel = 'alerta' | 'limite';

export interface AtRiskStudent {
  readonly student_id: number;
  readonly student_code: string | null;
  readonly student_name: string;
  readonly course_id: number;
  readonly course_code: string;
  readonly course_name: string;
  readonly sessions_held: number;
  readonly absences: number;
  readonly justified_absences: number;
  readonly lates: number;
  readonly absence_percent: number;
  readonly nivel: DpiLevel | null;
}

@Injectable({ providedIn: 'root' })
export class DpiApi extends BaseApi {
  atRisk(level: DpiLevel, courseId?: number | null) {
    return this.get<AtRiskStudent[]>('/dpi/at-risk', { level, course_id: courseId });
  }
}
