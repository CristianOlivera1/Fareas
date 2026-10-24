import { Component } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';

import { QueryParams } from './query-params';

@Component({ standalone: true, template: '' })
class RoutePage {}

describe('QueryParams', () => {
  let router: Router;
  let queryParams: QueryParams;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      providers: [provideRouter([{ path: 'admin/faces', component: RoutePage }])],
    }).compileComponents();

    router = TestBed.inject(Router);
    await router.navigateByUrl('/admin/faces?tab=enrollment#student-list');
    queryParams = TestBed.inject(QueryParams);
  });

  it('updates query values while preserving the current route, other parameters, and fragment', async () => {
    await queryParams.update({ student: 42 });

    const url = router.parseUrl(router.url);
    expect(url.root.children['primary'].segments.map((segment) => segment.path)).toEqual([
      'admin',
      'faces',
    ]);
    expect(url.queryParamMap.get('student')).toBe('42');
    expect(url.queryParamMap.get('tab')).toBe('enrollment');
    expect(url.fragment).toBe('student-list');
  });

  it('keeps rapid updates and omits the first page from the URL', async () => {
    await Promise.all([
      queryParams.update({ q: 'Ana' }),
      queryParams.update({ student: 42, page: 1 }),
    ]);

    const params = router.parseUrl(router.url).queryParamMap;
    expect(params.get('q')).toBe('Ana');
    expect(params.get('student')).toBe('42');
    expect(params.has('page')).toBe(false);
  });

  it('returns only positive integer query values', async () => {
    await queryParams.update({ student: '12.5' });
    expect(queryParams.integer('student', 0)()).toBe(0);

    await queryParams.update({ student: 12 });
    expect(queryParams.integer('student', 0)()).toBe(12);
  });
});
