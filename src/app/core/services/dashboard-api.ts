import { Injectable } from '@angular/core';

import { BaseApi } from '../api/api-url';

export interface DashboardSummary {
  readonly asistencias_hoy: number;
  readonly tardanzas_hoy: number;
  readonly ausencias_hoy: number;
  readonly total_marcas_hoy: number;
  readonly pct_ausentismo: number;
  readonly camaras_total: number;
  readonly camaras_activas: number;
  readonly streams_caidos: number;
  readonly alertas_dpi: number;
  readonly en_riesgo: number;
  readonly sessions_to_review: number;
  readonly at: string;
}

export interface HourlyPoint {
  readonly hour: string;
  readonly asistio: number;
  readonly tardanza: number;
  readonly falta: number;
  readonly total: number;
}

export interface AttendanceDistribution {
  readonly asistio: number;
  readonly tardanza: number;
  readonly falta: number;
  readonly sin_registro: number;
}

@Injectable({ providedIn: 'root' })
export class DashboardApi extends BaseApi {
  summary() {
    return this.get<DashboardSummary>('/dashboard/summary');
  }

  hourly(day?: string) {
    return this.get<HourlyPoint[]>('/stats/hourly', { day });
  }

  distribution() {
    return this.get<AttendanceDistribution>('/stats/distribution');
  }
}
