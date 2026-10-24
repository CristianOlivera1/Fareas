export interface EnrollmentBlock {
  readonly weekday: number;
  readonly start_time: string;
  readonly end_time: string;
  readonly room_code: string | null;
}

export interface PackageCourse {
  readonly course_id: number;
  readonly course_code: string;
  readonly course_name: string;
  readonly group_id: number | null;
  readonly group_code: string;
  readonly teacher_name: string | null;
  readonly capacity: number;
  readonly enrolled: number;
  readonly free: number;
  readonly blocks: EnrollmentBlock[];
}

export interface MissingCourse {
  readonly course_id: number;
  readonly course_code: string;
  readonly course_name: string;
}

export interface CyclePackage {
  readonly period: string;
  readonly cycle: number;
  readonly group_code: string;
  readonly courses: PackageCourse[];
  readonly missing: MissingCourse[];
}

export interface PackageLetter {
  readonly group_code: string;
  readonly courses_covered: number;
  readonly courses_total: number;
}

export interface ResolvedStudent {
  readonly id: number;
  readonly code: string | null;
  readonly full_name: string;
  readonly semester: number | null;
}

export interface ResolveResult {
  readonly found: ResolvedStudent[];
  readonly unknown: string[];
}

export type PairStatus = 'ok' | 'skipped' | 'failed';

export interface EnrollmentPair {
  readonly student_id: number;
  readonly student_code: string | null;
  readonly student_name: string;
  readonly group_id: number;
  readonly course_code: string;
  readonly group_code: string;
  readonly status: PairStatus;
  readonly reason: string | null;
}

export interface BulkResult {
  readonly students: number;
  readonly groups: number;
  readonly ok: number;
  readonly skipped: number;
  readonly failed: number;
  readonly unknown: string[];
  readonly missing: MissingCourse[];
  readonly results: EnrollmentPair[];
}

export interface EnrollmentWindow {
  readonly open: boolean;
  readonly start: string | null;
  readonly end: string | null;
  readonly message: string;
}

export interface EnrollmentStatus {
  readonly period: string;
  readonly student_cycle: number | null;
  readonly window: EnrollmentWindow;
  readonly enrolled_groups: number;
}

export interface OfferGroup {
  readonly group_id: number;
  readonly course_id: number;
  readonly course_code: string;
  readonly course_name: string;
  readonly cycle: number;
  readonly group_code: string;
  readonly teacher_name: string | null;
  readonly capacity: number;
  readonly enrolled: number;
  readonly free: number;
  readonly full: boolean;
  readonly blocks: EnrollmentBlock[];
  readonly mine: boolean;
  readonly current_group_code: string | null;
  readonly conflict: string | null;
}
