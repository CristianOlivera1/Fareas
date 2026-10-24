import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { describe, expect, it } from 'vitest';

import { filenameFromDisposition } from '../../shared/utils/download';
import { ReportsApi } from './reports-api';

describe('filenameFromDisposition', () => {
  it('reads a quoted filename', () => {
    expect(filenameFromDisposition('attachment; filename="asistencia_2026.xlsx"', 'x.xlsx')).toBe(
      'asistencia_2026.xlsx',
    );
  });

  it('falls back when the header is missing', () => {
    expect(filenameFromDisposition(null, 'asistencia.pdf')).toBe('asistencia.pdf');
  });
});

describe('ReportsApi', () => {
  function setup() {
    TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting()] });
    return { api: TestBed.inject(ReportsApi), http: TestBed.inject(HttpTestingController) };
  }

  it('requests the attendance report as a blob with the filters', () => {
    const { api, http } = setup();
    let result: { filename: string } | undefined;
    api.attendance('pdf', { desde: '2026-10-01', hasta: '2026-10-23', course_id: 3 }).subscribe((file) => (result = file));

    const req = http.expectOne((r) => r.url.endsWith('/reports/attendance.pdf'));
    expect(req.request.responseType).toBe('blob');
    expect(req.request.params.get('desde')).toBe('2026-10-01');
    expect(req.request.params.get('course_id')).toBe('3');
    req.flush(new Blob(['%PDF-']), {
      headers: { 'Content-Disposition': 'attachment; filename="asistencia_x.pdf"' },
    });

    expect(result?.filename).toBe('asistencia_x.pdf');
    http.verify();
  });

  it('omits the course filter for the DPI risk report when none is chosen', () => {
    const { api, http } = setup();
    api.dpiRisk(null).subscribe();
    const req = http.expectOne((r) => r.url.endsWith('/reports/dpi-risk.xlsx'));
    expect(req.request.params.has('course_id')).toBe(false);
    req.flush(new Blob(['x']));
    http.verify();
  });
});
