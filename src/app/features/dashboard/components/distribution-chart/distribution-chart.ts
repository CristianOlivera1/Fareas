import {
  AfterViewInit,
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  OnDestroy,
  computed,
  signal,
  viewChild,
} from '@angular/core';
import { Chart, registerables } from 'chart.js';
import { CommonModule } from '@angular/common';

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
  readonly slices = signal<Slice[]>([
    { label: 'Asistió', count: 1248, color: '#22c55e' },
    { label: 'Tardanza', count: 142, color: '#f59e0b' },
    { label: 'Sin registro', count: 87, color: '#9ca3af' },
    { label: 'Falta', count: 23, color: '#ef4444' },
  ]);

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
