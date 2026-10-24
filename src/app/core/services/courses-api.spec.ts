import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { describe, expect, it } from 'vitest';

import { CoursesApi } from './courses-api';

const API = 'http://localhost:8000/api/v1';

describe('CoursesApi course-level scheduling', () => {
  function setup() {
    TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting()] });
    return { api: TestBed.inject(CoursesApi), http: TestBed.inject(HttpTestingController) };
  }

  it('adds a block to a course without choosing a group or a teacher', () => {
    const { api, http } = setup();
    let created: { group_code: string; group_created: boolean } | undefined;
    api
      .createCourseBlock(7, { weekday: 1, start_time: '08:00', end_time: '10:00', room_id: 3, teacher_id: null })
      .subscribe((block) => (created = block));

    const request = http.expectOne(`${API}/courses/7/blocks`);
    expect(request.request.method).toBe('POST');
    expect(request.request.body).toEqual({ weekday: 1, start_time: '08:00', end_time: '10:00', room_id: 3, teacher_id: null });
    request.flush({ id: 1, group_id: 9, group_code: 'A', group_created: true });

    expect(created?.group_created).toBe(true);
    http.verify();
  });

  it('creates a group without a teacher and assigns one later', () => {
    const { api, http } = setup();
    api.createGroup(7, { group_code: 'B', teacher_id: null, capacity: 40 }).subscribe();
    http.expectOne(`${API}/courses/7/groups`).flush({});

    api.updateGroup(9, { teacher_id: 4 }).subscribe();
    const patch = http.expectOne(`${API}/groups/9`);
    expect(patch.request.method).toBe('PATCH');
    expect(patch.request.body).toEqual({ teacher_id: 4 });
    patch.flush({});
    http.verify();
  });

  it('lists the courses whose groups are all full', () => {
    const { api, http } = setup();
    api.overflowCourses().subscribe();
    http.expectOne(`${API}/courses/overflow`).flush([]);
    http.verify();
  });
});
