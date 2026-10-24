import { ChangeDetectionStrategy, Component, CUSTOM_ELEMENTS_SCHEMA, DestroyRef, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { RouterLink } from '@angular/router';
import { catchError, interval, of, startWith, switchMap } from 'rxjs';

import { DashboardApi, DashboardSummary } from '../../core/services/dashboard-api';
import { AuthService } from '../../core/services/auth/auth';
import { UiCard } from '../../shared/components/ui-card/ui-card';
import { ActivityFeed } from './components/activity-feed/activity-feed';
import { HourlyChart } from './components/hourly-chart/hourly-chart';
import { DistributionChart } from './components/distribution-chart/distribution-chart';
import { StudentList } from './components/student-list/student-list';

const REFRESH_MS = 30_000;

interface StatCard {
  title: string;
  value: string;
  detail: string;
  icon: string;
  accent: string;
}

function buildCards(summary: DashboardSummary | null): StatCard[] {
  const dash = '—';
  return [
    {
      title: 'Asistencias hoy',
      value: summary ? String(summary.asistencias_hoy) : dash,
      detail: summary ? `${summary.tardanzas_hoy} tardanzas` : 'Sin datos',
      icon: 'material-symbols:fact-check-outline',
      accent: 'text-green-600',
    },
    {
      title: 'Ausencias',
      value: summary ? String(summary.ausencias_hoy) : dash,
      detail: summary ? `${summary.pct_ausentismo}% de las marcas de hoy` : 'Sin datos',
      icon: 'material-symbols:person-off-outline',
      accent: 'text-red-500',
    },
    {
      title: 'Cámaras activas',
      value: summary ? `${summary.camaras_activas} / ${summary.camaras_total}` : dash,
      detail: summary
        ? summary.streams_caidos > 0
          ? `${summary.streams_caidos} cámaras sin conexión`
          : 'Todas las cámaras operan'
        : 'Sin datos',
      icon: 'material-symbols:videocam-outline',
      accent: 'text-(--fareas-primary)',
    },
    {
      title: 'Exceso de inasistencias',
      value: summary ? String(summary.alertas_dpi) : dash,
      detail: summary ? `${summary.en_riesgo} más en riesgo (≥ 20%)` : 'Sin datos',
      icon: 'akar-icons:triangle-alert-fill',
      accent: 'text-red-500',
    },
  ];
}

@Component({
  selector: 'app-dashboard',
  imports: [UiCard, RouterLink, ActivityFeed, HourlyChart, DistributionChart, StudentList],
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  templateUrl: './dashboard.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { class: 'block' },
})
export class Dashboard {
  private readonly api = inject(DashboardApi);
  private readonly destroyRef = inject(DestroyRef);
  protected readonly auth = inject(AuthService);

  readonly summary = signal<DashboardSummary | null>(null);
  readonly cards = computed(() => buildCards(this.summary()));
  readonly sessionsToReview = computed(() => this.summary()?.sessions_to_review ?? 0);
  readonly fullCourses = computed(() => this.summary()?.cursos_llenos ?? 0);

  constructor() {
    interval(REFRESH_MS)
      .pipe(
        startWith(0),
        switchMap(() => this.api.summary().pipe(catchError(() => of(null)))),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe((summary) => {
        if (summary) this.summary.set(summary);
      });
  }
}
