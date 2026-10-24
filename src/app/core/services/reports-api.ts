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

export type ReportFormat = 'pdf' | 'xlsx' | 'csv';
export type ReportTone = 'ok' | 'warn' | 'bad' | 'info' | 'muted';

export interface ReportCatalogItem {
  readonly key: string;
  readonly title: string;
  readonly description: string;
  readonly icon: string;
  readonly formats: ReportFormat[];
  readonly filters: string[];
}

export interface ReportQuery {
  readonly desde?: string | null;
  readonly hasta?: string | null;
  readonly cycle?: number | null;
  readonly course_id?: number | null;
  readonly group_id?: number | null;
  readonly teacher_id?: number | null;
  readonly room_id?: number | null;
  readonly status?: string | null;
  readonly q?: string | null;
  readonly only_risk?: boolean | null;
}

export interface ReportCell {
  readonly value: string | number | null;
  readonly tone: ReportTone | null;
}

export interface ReportPreview {
  readonly key: string;
  readonly title: string;
  readonly description: string;
  readonly filters: { readonly label: string; readonly value: string }[];
  readonly indicators: { readonly label: string; readonly value: string; readonly tone: ReportTone }[];
  readonly columns: { readonly key: string; readonly title: string; readonly align: 'left' | 'center' | 'right' }[];
  readonly rows: ReportCell[][];
  readonly total: number;
  readonly truncated: boolean;
}

export type ScheduleExportFormat = 'pdf' | 'xlsx' | 'png';

export interface ScheduleExportFilters extends ListParams {
  readonly format: ScheduleExportFormat;
  readonly semester?: string | null;
  readonly cycle?: number | null;
  readonly course_id?: number | null;
  readonly teacher_id?: number | null;
  readonly room_id?: number | null;
  readonly show_teacher?: boolean;
  readonly show_room?: boolean;
}

@Injectable({ providedIn: 'root' })
export class ReportsApi extends BaseApi {
  attendance(format: 'xlsx' | 'pdf', filters: AttendanceReportFilters) {
    return this.download(`/reports/attendance.${format}`, filters, `asistencia.${format}`);
  }

  catalog() {
    return this.get<ReportCatalogItem[]>('/reports/catalog');
  }

  preview(kind: string, query: ReportQuery) {
    return this.get<ReportPreview>('/reports/preview', { kind, ...query });
  }

  export(kind: string, format: ReportFormat, query: ReportQuery) {
    return this.download('/reports/export', { kind, format, ...query }, `reporte.${format}`);
  }

  groupMatrix(groupId: number) {
    return this.download('/reports/group-matrix.xlsx', { group_id: groupId }, 'registro-grupo.xlsx');
  }

  dpiRisk(courseId?: number | null) {
    return this.download('/reports/dpi-risk.xlsx', { course_id: courseId }, 'riesgo-dpi.xlsx');
  }

  schedule(filters: ScheduleExportFilters) {
    return this.download('/schedule/export', filters, `horario.${filters.format}`);
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
