"""Reconocimiento: similitud de coseno contra la galería de embeddings vigentes.

``FaceGallery`` mantiene en memoria los embeddings con ``is_current=TRUE``
(caché; se recarga con ``reload()`` tras cada enrolamiento). El pipeline la
recibe como dependencia; este módulo no toca la BD.
"""
import numpy as np

from app.tables import FaceEmbedding


def parse_pg_array(value) -> np.ndarray | None:
    """Valor de la columna REAL[512] → np.ndarray float32.

    Con asyncpg la lectura entrega ``list[float]`` nativo (el modelo mapea la
    columna con PgRealArray); se conserva el soporte del literal str
    '{0.1,0.2,...}' por robustez (pgAdmin, dumps, drivers futuros).
    """
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
    """Galería de embeddings L2-normalizados (student_id → matriz (n, 512))."""

    def __init__(self) -> None:
        self._embs: dict[int, np.ndarray] = {}

    def set_student(self, student_id: int, vectors: list[np.ndarray]) -> None:
        """Inserta/actualiza un alumno (p. ej. tras enrolarlo)."""
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
        """Recarga la galería desde filas de face_embedding (is_current)."""
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
        """Mejor coincidencia dentro de ``candidates`` (o toda la galería).

        Devuelve (student_id | None, similitud). ``None`` = DESCONOCIDO.
        """
        if not self._embs:
            return None, 0.0
        pool = self._embs if candidates is None else {sid: m for sid, m in self._embs.items() if sid in candidates}
        if not pool:
            return None, 0.0
        best_sid, best_sim = None, 0.0
        for sid, mat in pool.items():
            sim = float((mat @ embedding).max())  # máx entre los embeddings del alumno
            if sim > best_sim:
                best_sid, best_sim = sid, sim
        if best_sid is not None and best_sim >= threshold:
            return best_sid, best_sim
        return None, best_sim
