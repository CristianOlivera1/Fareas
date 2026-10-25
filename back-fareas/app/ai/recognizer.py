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
        self._stacked: tuple[list[int], np.ndarray, np.ndarray] | None = None

    def set_student(self, student_id: int, vectors: list[np.ndarray]) -> None:
        if vectors:
            self._embs[student_id] = np.stack(vectors)
        else:
            self._embs.pop(student_id, None)
        self._stacked = None

    def remove_student(self, student_id: int) -> None:
        self._embs.pop(student_id, None)
        self._stacked = None

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
        self._stacked = None

    def _stack(self) -> tuple[list[int], np.ndarray, np.ndarray]:
        if self._stacked is None:
            ids = list(self._embs)
            matrix = np.concatenate([self._embs[sid] for sid in ids]) if ids else np.empty((0, 512), dtype=np.float32)
            counts = np.array([self._embs[sid].shape[0] for sid in ids], dtype=np.int64)
            starts = np.concatenate(([0], np.cumsum(counts)[:-1])) if ids else np.empty(0, dtype=np.int64)
            self._stacked = (ids, matrix, starts)
        return self._stacked

    def best_similarities(self, embedding: np.ndarray) -> dict[int, float]:
        ids, matrix, starts = self._stack()
        if not ids:
            return {}
        best = np.maximum.reduceat(matrix @ embedding, starts)
        return dict(zip(ids, best.tolist(), strict=True))

    def identify(
        self,
        embedding: np.ndarray,
        candidates: set[int] | None = None,
        threshold: float = 0.75,
        margin: float = 0.0,
    ) -> tuple[int | None, float]:
        if not self._embs:
            return None, 0.0
        scores = self.best_similarities(embedding)
        pool = scores if candidates is None else {sid: sim for sid, sim in scores.items() if sid in candidates}
        if not pool:
            return None, 0.0
        best_sid = max(pool, key=pool.__getitem__)
        best_sim = pool[best_sid]
        if best_sim < threshold:
            return None, best_sim
        rival = max((sim for sid, sim in scores.items() if sid != best_sid), default=0.0)
        if best_sim - rival < margin:
            return None, best_sim
        return best_sid, best_sim
