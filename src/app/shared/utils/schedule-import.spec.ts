import type { ScheduleImportRow } from '../../core/models/imports';
import { groupScheduleImportRows, scheduleImportRowIssues } from './schedule-import';

function createRow(overrides: Partial<ScheduleImportRow> = {}): ScheduleImportRow {
  return {
    key: 'block-1',
    course_code: 'TSTUI901',
    course_name: 'Algebra lineal',
    group_code: 'A',
    weekday: 1,
    start_time: '08:00',
    end_time: '10:00',
    teacher_id: null,
    room_id: null,
    teacher_name: null,
    room_code: null,
    course_suggestion: null,
    suggestion_dismissed: true,
    confiable: true,
    nota: null,
    linea: '',
    pagina: 1,
    ...overrides,
  };
}

describe('schedule import utilities', () => {
  it('accepts a valid block within the configured hours', () => {
    expect(scheduleImportRowIssues(createRow(), '07:00', '20:00')).toEqual([]);
  });

  it('groups and sorts rows by course, then by weekday and start time', () => {
    const rows = [
      createRow({ key: 'later', weekday: 2, start_time: '10:00' }),
      createRow({ key: 'earlier', weekday: 1, start_time: '08:00' }),
      createRow({ key: 'another-course', course_code: 'TSTUI902' }),
    ];

    expect(groupScheduleImportRows(rows)).toEqual([
      {
        code: 'TSTUI901',
        name: 'Algebra lineal',
        rows: [rows[1], rows[0]],
      },
      {
        code: 'TSTUI902',
        name: 'Algebra lineal',
        rows: [rows[2]],
      },
    ]);
  });

  it('reports invalid schedule fields and preserves the configured hour limits', () => {
    const issues = scheduleImportRowIssues(
      createRow({
        course_code: 'A',
        group_code: '',
        weekday: 7,
        start_time: '06:00',
        end_time: '09:00',
      }),
      '07:00',
      '20:00',
    );

    expect(issues).toContain('Código de curso de 3 a 20 caracteres');
    expect(issues).toContain('Grupo de 1 a 5 caracteres');
    expect(issues).toContain('Día de lunes a viernes');
    expect(issues).toContain('El bloque no puede durar más de 2 horas');
    expect(issues).toContain('La clase empieza antes de 07:00');
  });

  it('rejects malformed times', () => {
    expect(
      scheduleImportRowIssues(createRow({ start_time: '25:00' }), '07:00', '20:00'),
    ).toContain('Hora de inicio y fin válidas');
  });
});
