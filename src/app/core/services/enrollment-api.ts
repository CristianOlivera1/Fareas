import { Injectable } from '@angular/core';

import { BaseApi } from '../api/api-url';
import {
  BulkResult,
  CyclePackage,
  EnrollmentStatus,
  OfferGroup,
  PackageLetter,
  ResolveResult,
  SelectionItem,
  SelectionOutcome,
} from '../models/enrollment';

export interface StudentRefs {
  readonly student_ids?: number[];
  readonly student_codes?: string[];
}

@Injectable({ providedIn: 'root' })
export class EnrollmentApi extends BaseApi {
  letters(cycle: number) {
    return this.get<PackageLetter[]>('/enrollment/package-letters', { cycle });
  }

  packagePreview(cycle: number, groupCode: string) {
    return this.get<CyclePackage>('/enrollment/package', { cycle, group_code: groupCode });
  }

  resolveStudents(codes: string[]) {
    return this.post<ResolveResult>('/enrollment/resolve-students', { codes });
  }

  enrollPackage(refs: StudentRefs, cycle: number, groupCode: string) {
    return this.post<BulkResult>('/enrollment/package', { ...refs, cycle, group_code: groupCode });
  }

  enrollBulk(refs: StudentRefs, groupIds: number[]) {
    return this.post<BulkResult>('/enrollment/bulk', { ...refs, group_ids: groupIds });
  }

  myStatus() {
    return this.get<EnrollmentStatus>('/me/enrollment');
  }

  myOffer(cycle?: number | null) {
    return this.get<OfferGroup[]>('/me/enrollment/offer', { cycle });
  }

  enrollMe(groupId: number) {
    return this.post<{ message: string }>('/me/enrollment', { group_id: groupId });
  }

  withdrawMe(groupId: number) {
    return this.delete<{ message: string }>(`/me/enrollment/${groupId}`);
  }

  switchMine(fromGroupId: number, toGroupId: number) {
    return this.post<{ student_id: number }>(`/me/enrollment/${fromGroupId}/transfer`, {
      destino_group_id: toGroupId,
    });
  }

  updateMyCycle(cycle: number) {
    return this.patch<{ student_cycle: number }>('/me/enrollment/cycle', { cycle });
  }

  enrollSelection(items: SelectionItem[]) {
    return this.post<SelectionOutcome>('/me/enrollment/bulk', { items });
  }
}
