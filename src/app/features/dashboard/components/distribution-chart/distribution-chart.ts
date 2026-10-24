import {
  AfterViewInit,
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  OnDestroy,
  computed,
  effect,
  inject,
  signal,
  viewChild,
} from '@angular/core';
import { Chart, registerables } from 'chart.js';
import { CommonModule } from '@angular/common';
import { AttendanceDistribution, DashboardApi } from '../../../../core/services/dashboard-api';

Chart.register(...registerables);

interface Slice {
  label: string;
  count: number;
  color: string;
}

@Component({
  selector: 'app-distribution-chart',
  imports: [CommonModule],
  templateUrl: './distribution-chart.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { class: 'block' },
})
export class DistributionChart implements AfterViewInit, OnDestroy {
  private readonly api = inject(DashboardApi);

  readonly distribution = signal<AttendanceDistribution>({
    asistio: 0,
    tardanza: 0,
    falta: 0,
    sin_registro: 0,
  });

  readonly slices = computed<Slice[]>(() => {
    const data = this.distribution();
    return [
      { label: 'Asistió', count: data.asistio, color: '#22c55e' },
      { label: 'Tardanza', count: data.tardanza, color: '#f59e0b' },
      { label: 'Sin registro', count: data.sin_registro, color: '#9ca3af' },
      { label: 'Falta', count: data.falta, color: '#ef4444' },
    ];
  });

  readonly total = computed(() => this.slices().reduce((acc, slice) => acc + slice.count, 0));
  readonly attendanceRate = computed(() => {
    const total = this.total();
    const present = this.slices()[0].count;
    return total === 0 ? '0%' : `${((present / total) * 100).toFixed(1)}%`;
  });

  readonly legend = computed(() =>
    this.slices().map((slice) => ({
      ...slice,
      percent: this.total() === 0 ? '0%' : `${((slice.count / this.total()) * 100).toFixed(1)}%`,
    })),
  );

  private readonly canvas = viewChild.required<ElementRef<HTMLCanvasElement>>('chart');
  private chart?: Chart<'doughnut'>;

  constructor() {
    this.api.distribution().subscribe({ next: (data) => this.distribution.set(data) });

    effect(() => {
      const slices = this.slices();
      if (!this.chart) return;
      this.chart.data.datasets[0].data = slices.map((slice) => slice.count);
      this.chart.update();
    });
  }

  ngAfterViewInit(): void {
    const slices = this.slices();
    this.chart = new Chart(this.canvas().nativeElement, {
      type: 'doughnut',
      data: {
        labels: slices.map((slice) => slice.label),
        datasets: [
          {
            data: slices.map((slice) => slice.count),
            backgroundColor: slices.map((slice) => slice.color),
            borderWidth: 3,
            borderColor: '#ffffff',
            hoverOffset: 6,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: '72%',
        plugins: { legend: { display: false } },
      },
    });
  }

  ngOnDestroy(): void {
    this.chart?.destroy();
  }
}
