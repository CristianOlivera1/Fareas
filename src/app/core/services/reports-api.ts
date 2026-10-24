import { Injectable } from '@angular/core';
import { map } from 'rxjs';

import { apiUrl, BaseApi, ListParams, toParams } from '../api/api-url';
import { filenameFromDisposition } from '../../shared/utils/download';

export interface ReportFile {
  readonly blob: Blob;
  readonly filename: string;
}

export interface AttendanceReportFilters extends ListParams {
  readonly desde?: string | null;
  readonly hasta?: string | null;
  readonly course_id?: number | null;
}

@Injectable({ providedIn: 'root' })
export class ReportsApi extends BaseApi {
  attendance(format: 'xlsx' | 'pdf', filters: AttendanceReportFilters) {
    return this.download(`/reports/attendance.${format}`, filters, `asistencia.${format}`);
  }

  groupMatrix(groupId: number) {
    return this.download('/reports/group-matrix.xlsx', { group_id: groupId }, 'registro-grupo.xlsx');
  }

  dpiRisk(courseId?: number | null) {
    return this.download('/reports/dpi-risk.xlsx', { course_id: courseId }, 'riesgo-dpi.xlsx');
  }

  private download(path: string, params: ListParams, fallbackName: string) {
    return this.http
      .get(apiUrl(path), { params: toParams(params), responseType: 'blob', observe: 'response' })
      .pipe(
        map((response): ReportFile => ({
          blob: response.body as Blob,
          filename: filenameFromDisposition(
            response.headers.get('Content-Disposition'),
            fallbackName,
          ),
        })),
      );
  }
}
