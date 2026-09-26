import { TestBed } from '@angular/core/testing';

import { DataTable } from './data-table';

describe('DataTable', () => {
  let component: DataTable;

  beforeEach(() => {
    TestBed.configureTestingModule({});
    component = TestBed.runInInjectionContext(() => new DataTable());
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
