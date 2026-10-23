import { Injectable } from '@angular/core';

import { BaseApi } from '../api/api-url';
import { FaceDeleted, FaceEnrollment, FaceStatus } from '../models/faces';

@Injectable({
  providedIn: 'root',
})
export class FacesApi extends BaseApi {
  status(studentId: number) {
    return this.get<FaceStatus>(`/students/${studentId}/faces`);
  }

  enroll(studentId: number, photos: string[], consent: boolean) {
    return this.post<FaceEnrollment>(`/students/${studentId}/faces`, { photos, consent });
  }

  remove(studentId: number) {
    return this.delete<FaceDeleted>(`/students/${studentId}/faces`);
  }
}
