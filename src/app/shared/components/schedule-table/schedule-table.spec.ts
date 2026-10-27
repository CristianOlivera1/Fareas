import { TestBed } from '@angular/core/testing';

import { ScheduleEntry, ScheduleTable } from './schedule-table';

function entry(overrides: Partial<ScheduleEntry>): ScheduleEntry {
  return {
    id: 1,
    weekday: 1,
    start_time: '07:00',
    end_time: '09:00',
    course_code: 'AIS32',
    group_code: 'A',
    room_code: 'LAB 303',
    ...overrides,
  };
}

function render(entries: ScheduleEntry[]): HTMLElement {
  const fixture = TestBed.createComponent(ScheduleTable);
  fixture.componentRef.setInput('entries', entries);
  fixture.componentRef.setInput('days', [1, 2]);
  fixture.componentRef.setInput('hourFrom', 7);
  fixture.componentRef.setInput('hourTo', 11);
  fixture.detectChanges();
  return fixture.nativeElement as HTMLElement;
}

describe('ScheduleTable', () => {
  it('spans a two-hour block over both hours', () => {
    const cell = render([entry({})]).querySelector('td[rowspan="2"]');

    expect(cell?.querySelectorAll('.chip').length).toBe(1);
  });

  it('shows parallel groups side by side across the whole slot', () => {
    const host = render([entry({ id: 1, group_code: 'A' }), entry({ id: 2, group_code: 'B', room_code: 'LAB 401' })]);
    const cell = host.querySelector('td[rowspan="2"]');

    expect(cell?.querySelectorAll('.chip').length).toBe(2);
    expect(host.querySelectorAll('tbody tr')[1].querySelectorAll('td').length).toBe(1);
  });

  it('merges partially overlapping blocks into one span', () => {
    const host = render([
      entry({ id: 1, start_time: '07:00', end_time: '09:00' }),
      entry({ id: 2, start_time: '08:00', end_time: '10:00', group_code: 'B' }),
    ]);
    const cell = host.querySelector('td[rowspan="3"]');

    expect(cell?.querySelectorAll('.chip').length).toBe(2);
  });
});
