import { ChangeDetectionStrategy, Component, signal } from '@angular/core';
import { UiCard } from '../../shared/components/ui-card/ui-card';
import { ActivityFeed } from './components/activity-feed/activity-feed';
import { HourlyChart } from './components/hourly-chart/hourly-chart';
import { DistributionChart } from './components/distribution-chart/distribution-chart';
import { StudentList } from './components/student-list/student-list';

interface StatCard {
  title: string;
  value: string;
  detail: string;
  icon: string;
  accent: string;
}

@Component({
  selector: 'app-dashboard',
  imports: [UiCard, ActivityFeed, HourlyChart, DistributionChart, StudentList],
  templateUrl: './dashboard.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { class: 'block' },
})
export class Dashboard {
  readonly cards = signal<StatCard[]>([
    {
      title: 'Asistencias hoy',
      value: '128',
      detail: '12 tardanzas',
      icon: 'material-symbols:fact-check-outline',
      accent: 'text-green-600',
    },
    {
      title: 'Ausencias',
      value: '11',
      detail: '7.7% del plantel',
      icon: 'material-symbols:person-off-outline',
      accent: 'text-red-500',
    },
    {
      title: 'Cámaras activas',
      value: '14 / 16',
      detail: '2 streams RTSP caídos',
      icon: 'material-symbols:videocam-outline',
      accent: 'text-(--fareas-primary)',
    },
    {
      title: 'Alertas críticas DPI',
      value: '3',
      detail: 'Alumnos con >30% faltas',
      icon: 'akar-icons:triangle-alert-fill',
      accent: 'text-red-500',
    }
  ]);
}
