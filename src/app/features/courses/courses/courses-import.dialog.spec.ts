import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { MessageService } from 'primeng/api';

import { CurriculumPreview, CurriculumPreviewRow } from '../../../core/models/imports';
import { CoursesImportDialog } from './courses-import.dialog';

const API = 'http://localhost:8000/api/v1';

function row(overrides: Partial<CurriculumPreviewRow>): CurriculumPreviewRow {
  return {
    fila: 1,
    code: 'AIS11',
    name: 'Introducción a la informática',
    cycle: 1,
    confiable: true,
    nota: null,
    linea: '',
    pagina: 1,
    ya_existe: false,
    existente: null,
    ...overrides,
  };
}

function preview(rows: CurriculumPreviewRow[]): CurriculumPreview {
  return {
    tipo: 'imagen',
    paginas: 1,
    total: rows.length,
    listos: rows.length,
    por_revisar: 0,
    ya_existentes: rows.filter((item) => item.ya_existe).length,
    ciclos: [1, 2],
    cursos: rows,
  };
}

describe('CoursesImportDialog', () => {
  let component: CoursesImportDialog;
  let httpMock: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [CoursesImportDialog],
      providers: [provideHttpClient(), provideHttpClientTesting(), MessageService],
    }).compileComponents();
    component = TestBed.createComponent(CoursesImportDialog).componentInstance;
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => httpMock.verify());

  async function load(rows: CurriculumPreviewRow[], defaultCycle: number | null = null) {
    component.onFile(new File(['malla'], 'malla.png', { type: 'image/png' }));
    component.defaultCycle.set(defaultCycle);
    const reading = component.readCurriculum();
    const request = httpMock.expectOne(`${API}/courses/import-curriculum`);
    request.flush(preview(rows));
    await reading;
    return request.request;
  }

  it('sends the file and the optional default cycle', async () => {
    const request = await load([row({})], 4);

    const body = request.body as FormData;
    expect(body.get('file')).toBeInstanceOf(File);
    expect(body.get('default_cycle')).toBe('4');
    expect(component.step()).toBe(2);
  });

  it('omits the default cycle when detection is automatic', async () => {
    const request = await load([row({})]);

    expect((request.body as FormData).has('default_cycle')).toBe(false);
  });

  it('groups the rows in tabs per cycle and filters them', async () => {
    await load([
      row({ fila: 1, code: 'AIS11', cycle: 1 }),
      row({ fila: 2, code: 'AGG1', name: 'Lengua castellana', cycle: 1 }),
      row({ fila: 3, code: 'AIS21', name: 'Análisis y diseño', cycle: 2 }),
    ]);

    expect(component.tabs().map((tab) => [tab.label, tab.count])).toEqual([
      ['Todos', 3],
      ['I', 2],
      ['II', 1],
    ]);
    component.setFilter(2);
    expect(component.visibleRows().map((item) => item.code)).toEqual(['AIS21']);
  });

  it('flags invalid and repeated rows and blocks the confirmation', async () => {
    await load([
      row({ fila: 1, code: 'AIS11' }),
      row({ fila: 2, code: 'AIS11', name: 'Otro curso' }),
      row({ fila: 3, code: 'AB', name: 'x', cycle: null }),
    ]);

    const [first, , invalid] = component.rows();
    expect(component.issues(first)).toEqual(['Código repetido en la lista']);
    expect(component.issues(invalid)).toEqual(['Código de 3 a 20 letras o números', 'Nombre del curso', 'Ciclo']);
    expect(component.canConfirm()).toBe(false);

    component.removeInvalid();
    expect(component.rows()).toHaveLength(0);
  });

  it('marks unreliable rows for review and clears the mark after an edit', async () => {
    await load([row({ confiable: false, nota: 'Lectura con poca confianza' })]);
    const [item] = component.rows();

    expect(component.statusOf(item)).toBe('review');
    component.onName(item.key, { target: { value: 'Introducción a la informática y sistemas' } } as unknown as Event);

    expect(component.statusOf(component.rows()[0])).toBe('ready');
  });

  it('keeps existing courses out of the confirmation and normalizes the codes', async () => {
    await load([
      row({ fila: 1, code: 'AIS11' }),
      row({
        fila: 2,
        code: 'AGG1',
        name: 'Lengua castellana',
        ya_existe: true,
        existente: { id: 7, name: 'Lengua', cycle: 1 },
      }),
    ]);
    component.onCode(component.rows()[0].key, { target: { value: 'ais-11 ' } } as unknown as Event);

    expect(component.canConfirm()).toBe(true);
    const confirming = component.confirm();
    const request = httpMock.expectOne(`${API}/courses/import-curriculum/confirm`);
    expect(request.request.body).toEqual({
      cursos: [{ code: 'AIS11', name: 'Introducción a la informática', cycle: 1 }],
    });
    request.flush({ creados: 1, omitidos: 0, codigos_creados: ['AIS11'], codigos_omitidos: [], total: 1 });
    await confirming;

    expect(component.step()).toBe(3);
    expect(component.result()?.creados).toBe(1);
  });

  it('adds a manual row in the current cycle tab', async () => {
    await load([row({ cycle: 2 })]);
    component.setFilter(2);

    component.addRow();

    const added = component.rows()[1];
    expect(added.cycle).toBe(2);
    expect(component.statusOf(added)).toBe('fix');
  });

  it('shows the backend message when the file cannot be read', async () => {
    component.onFile(new File(['x'], 'malla.png', { type: 'image/png' }));
    const reading = component.readCurriculum();
    httpMock
      .expectOne(`${API}/courses/import-curriculum`)
      .flush({ detail: 'No se reconocieron cursos.' }, { status: 422, statusText: 'Unprocessable' });
    await reading;

    expect(component.step()).toBe(1);
    expect(component.error()).toBe('No se reconocieron cursos.');
  });
});
