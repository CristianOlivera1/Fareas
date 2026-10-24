import {
  AfterViewInit,
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  OnDestroy,
  effect,
  inject,
  signal,
  viewChild,
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Chart, registerables } from 'chart.js';
import { Select } from 'primeng/select';
import { DashboardApi, HourlyPoint } from '../../../../core/services/dashboard-api';

Chart.register(...registerables);

function isoDay(offsetDays: number): string {
  const date = new Date();
  date.setDate(date.getDate() + offsetDays);
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${date.getFullYear()}-${month}-${day}`;
}

@Component({
  selector: 'app-hourly-chart',
  imports: [FormsModule, Select],
  templateUrl: './hourly-chart.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { class: 'block' },
})
export class HourlyChart implements AfterViewInit, OnDestroy {
  readonly period = signal<'Hoy' | 'Ayer'>('Hoy');
  readonly periodOptions = signal(['Hoy', 'Ayer']);

  private readonly api = inject(DashboardApi);
  private readonly points = signal<HourlyPoint[]>([]);

  private readonly canvas = viewChild.required<ElementRef<HTMLCanvasElement>>('chart');
  private chart?: Chart<'line'>;

  constructor() {
    effect(() => {
      const day = isoDay(this.period() === 'Ayer' ? -1 : 0);
      this.api.hourly(day).subscribe({
        next: (points) => this.points.set(points),
        error: () => this.points.set([]),
      });
    });

    effect(() => {
      const points = this.points();
      if (!this.chart) return;
      this.chart.data.labels = points.map((point) => point.hour);
      this.chart.data.datasets[0].data = points.map((point) => point.total);
      this.chart.update();
    });
  }

  ngAfterViewInit(): void {
    this.chart = new Chart(this.canvas().nativeElement, {
      type: 'line',
      data: {
        labels: this.points().map((point) => point.hour),
        datasets: [
          {
            data: this.points().map((point) => point.total),
            borderColor: '#155dfc',
            borderWidth: 2,
            fill: true,
            backgroundColor: (context) => {
              const { chart } = context;
              const { ctx, chartArea } = chart;
              if (!chartArea) return 'rgba(21, 93, 252, 0.12)';
              const gradient = ctx.createLinearGradient(0, chartArea.top, 0, chartArea.bottom);
              gradient.addColorStop(0, 'rgba(21, 93, 252, 0.25)');
              gradient.addColorStop(1, 'rgba(21, 93, 252, 0)');
              return gradient;
            },
            tension: 0.4,
            pointRadius: 0,
            pointHoverRadius: 4,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          y: {
            min: 0,
            ticks: { precision: 0, color: '#9ca3af', font: { size: 11 } },
            grid: { color: '#f1f5f9' },
          },
          x: {
            ticks: {
              color: '#9ca3af',
              font: { size: 11 },
              autoSkip: true,
              maxTicksLimit: 7,
              maxRotation: 0,
            },
            grid: { display: false },
          },
        },
      },
    });
  }

  ngOnDestroy(): void {
    this.chart?.destroy();
  }
}
