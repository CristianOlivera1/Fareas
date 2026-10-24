import { presetRange } from './date-range';

const WEDNESDAY = new Date(2026, 9, 21);

describe('presetRange', () => {
  it('covers today, the week from Monday and the month so far', () => {
    expect(presetRange('today', WEDNESDAY, null)).toEqual({ from: '2026-10-21', to: '2026-10-21' });
    expect(presetRange('week', WEDNESDAY, null)).toEqual({ from: '2026-10-19', to: '2026-10-21' });
    expect(presetRange('month', WEDNESDAY, null)).toEqual({ from: '2026-10-01', to: '2026-10-21' });
  });

  it('uses the last 30 days by default', () => {
    expect(presetRange('last30', WEDNESDAY, null)).toEqual({ from: '2026-09-21', to: '2026-10-21' });
  });

  it('starts at the semester start and never goes past today', () => {
    const semester = { start: '2026-08-10', end: '2026-12-20' };

    expect(presetRange('semester', WEDNESDAY, semester)).toEqual({ from: '2026-08-10', to: '2026-10-21' });
    expect(presetRange('semester', WEDNESDAY, { start: '2026-03-01', end: '2026-07-31' })).toEqual({
      from: '2026-03-01',
      to: '2026-07-31',
    });
  });

  it('falls back to 30 days when the semester has no dates', () => {
    expect(presetRange('semester', WEDNESDAY, { start: null, end: null }).from).toBe('2026-09-21');
  });
});
