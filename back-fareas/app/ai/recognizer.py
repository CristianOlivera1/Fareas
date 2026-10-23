import numpy as np

from app.tables import FaceEmbedding


def parse_pg_array(value) -> np.ndarray | None:
    if value is None:
        return None
    if isinstance(value, list | tuple):
        return np.asarray(value, dtype=np.float32)
    body = str(value).strip().strip("{}")
    if not body:
        return None
    try:
        return np.asarray([float(x) for x in body.split(",") if x != ""], dtype=np.float32)
    except ValueError:
        return None

class FaceGallery:
    def __init__(self) -> None:
        self._embs: dict[int, np.ndarray] = {}

    def set_student(self, student_id: int, vectors: list[np.ndarray]) -> None:
        if vectors:
            self._embs[student_id] = np.stack(vectors)
        else:
            self._embs.pop(student_id, None)

    def remove_student(self, student_id: int) -> None:
        self._embs.pop(student_id, None)

    @property
    def student_ids(self) -> set[int]:
        return set(self._embs)

    def __len__(self) -> int:
        return len(self._embs)

    def reload(self, rows: list[FaceEmbedding]) -> None:
        bucket: dict[int, list[np.ndarray]] = {}
        for r in rows:
            vec = parse_pg_array(r.vector)
            if vec is not None and vec.size == 512:
                bucket.setdefault(r.student_id, []).append(vec)
        self._embs = {sid: np.stack(v) for sid, v in bucket.items()}

    def identify(
        self,
        embedding: np.ndarray,
        candidates: set[int] | None = None,
        threshold: float = 0.75,
    ) -> tuple[int | None, float]:
        if not self._embs:
            return None, 0.0
        pool = self._embs if candidates is None else {sid: m for sid, m in self._embs.items() if sid in candidates}
        if not pool:
            return None, 0.0
        best_sid, best_sim = None, 0.0
        for sid, mat in pool.items():
            sim = float((mat @ embedding).max())
            if sim > best_sim:
                best_sid, best_sim = sid, sim
        if best_sid is not None and best_sim >= threshold:
            return best_sid, best_sim
        return None, best_sim
