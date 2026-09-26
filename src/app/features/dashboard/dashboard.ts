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
      title: 'Empleados activos',
      value: '142',
      detail: '3 de licencia',
      icon: 'material-symbols:group-outline',
      accent: 'text-(--fareas-primary)',
    },
    {
      title: 'Ausencias',
      value: '11',
      detail: '7.7% del plantel',
      icon: 'material-symbols:person-off-outline',
      accent: 'text-red-500',
    },
    {
      title: 'Reconocimiento facial',
      value: '98.2%',
      detail: 'precisión mock',
      icon: 'material-symbols:face-outline',
      accent: 'text-amber-600',
    },
  ]);
}
