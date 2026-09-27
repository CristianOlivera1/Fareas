import {
  AfterViewInit,
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  OnDestroy,
  effect,
  signal,
  viewChild,
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Chart, registerables } from 'chart.js';
import { Select } from 'primeng/select';

Chart.register(...registerables);

const HOURS = ['7:00', '8:00', '9:00', '10:00', '11:00', '12:00', '13:00', '14:00', '15:00', '16:00', '17:00', '18:00', '19:00'];

/** Registros de asistencia por hora de inicio de bloque (07:00–20:00). Escala de la facultad (~90 marcas/h). */
const MOCK_SERIES: Record<string, number[]> = {
  Hoy: [62, 78, 84, 90, 71, 55, 12, 0, 48, 66, 74, 31, 0],
  Ayer: [58, 74, 80, 87, 68, 52, 10, 0, 44, 60, 70, 28, 0],
};

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

  private readonly canvas = viewChild.required<ElementRef<HTMLCanvasElement>>('chart');
  private chart?: Chart<'line'>;

  constructor() {
    effect(() => {
      const period = this.period();
      if (this.chart) {
        this.chart.data.datasets[0].data = MOCK_SERIES[period];
        this.chart.update();
      }
    });
  }

  ngAfterViewInit(): void {
    this.chart = new Chart(this.canvas().nativeElement, {
      type: 'line',
      data: {
        labels: HOURS,
        datasets: [
          {
            data: MOCK_SERIES[this.period()],
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
            max: 100,
            ticks: { stepSize: 25, color: '#9ca3af', font: { size: 11 } },
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
