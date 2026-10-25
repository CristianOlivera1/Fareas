import { Injectable } from '@angular/core';
import { map } from 'rxjs';

import { apiUrl, BaseApi, toParams } from '../api/api-url';
import { filenameFromDisposition } from '../../shared/utils/download';

export interface PilotStudent {
  readonly id: number;
  readonly code: string | null;
  readonly name: string;
  readonly alias: string;
  readonly normal: number;
  readonly adversa: number;
}

export interface PilotRate {
  readonly count: number;
  readonly total: number;
  readonly value: number | null;
  readonly low: number | null;
  readonly high: number | null;
}

export interface PilotCurvePoint {
  readonly threshold: number;
  readonly far: number | null;
  readonly frr: number | null;
}

export interface PilotStatus {
  readonly camera_room: string | null;
  readonly students: PilotStudent[];
  readonly captures: number;
  readonly unenrolled_captures: number;
  readonly tar: PilotRate;
  readonly frr: PilotRate;
  readonly misidentified: PilotRate;
  readonly far: PilotRate;
  readonly curve: PilotCurvePoint[];
}

export interface PilotCapture {
  readonly capture_id: string;
  readonly frames: number;
  readonly alias: string;
  readonly condition: string;
}

export interface PilotCaptureRequest {
  readonly student_id: number | null;
  readonly condition: 'normal' | 'adversa';
  readonly seconds: number;
}

export interface PilotRules {
  readonly threshold: number;
  readonly margin: number;
  readonly confirm: number;
}

@Injectable({ providedIn: 'root' })
export class PilotApi extends BaseApi {
  status(rules: PilotRules) {
    return this.get<PilotStatus>('/pilot/status', { ...rules });
  }

  capture(request: PilotCaptureRequest) {
    return this.post<PilotCapture>('/pilot/captures', request);
  }

  reset() {
    return this.delete<void>('/pilot/data');
  }

  exportCsv() {
    return this.http
      .get(apiUrl('/pilot/export'), { params: toParams(), responseType: 'blob', observe: 'response' })
      .pipe(
        map((response) => ({
          blob: response.body as Blob,
          filename: filenameFromDisposition(response.headers.get('Content-Disposition'), 'pilot_data.csv'),
        })),
      );
  }
}
