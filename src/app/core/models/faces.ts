export interface FaceStatus {
  readonly student_id: number;
  readonly enrolled: boolean;
  readonly photo_url: string | null;
  readonly source: string | null;
  readonly created_at: string | null;
}

export interface FaceEnrollment {
  readonly student_id: number;
  readonly photos: number;
  readonly min_pair_similarity: number;
  readonly min_group_similarity: number;
  readonly photo_url: string | null;
  readonly embedding_id: number;
}

export interface FaceDeleted {
  readonly student_id: number;
  readonly deleted: number;
}
