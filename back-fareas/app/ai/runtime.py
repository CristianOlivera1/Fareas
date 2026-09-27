"""Modelos cargados UNA VEZ por proceso (detector + embedder + galería).

Los imports de ``onnxruntime`` son PESADOS, así que aquí son perezosos: el
módulo se importa gratis y los modelos se cargan en el primer uso real. El
Bloque 6 resolverá la galería por aula/sesión desde la BD; por ahora
`vision()` ofrece los objetos base y `recargar_galeria(db)` llena la caché
con los embeddings vigentes (usada por el enrolamiento RF-04).
"""
import os
import threading

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from app.ai.recognizer import FaceGallery
from app.core.config import get_settings
from app.tables import FaceEmbedding

_lock = threading.Lock()
_detector = None
_embedder = None
_gallery = FaceGallery()


def _model_path(filename: str) -> str:
    path = os.path.join(get_settings().MODELS_DIR, filename)
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"Falta el modelo {filename} en '{get_settings().MODELS_DIR}'. "
            "Copia el pack buffalo_l (ver PLAN §0)."
        )
    return path


def detector():
    global _detector
    if _detector is None:
        from app.ai.detector import ScrfdDetector  # import perezoso (onnxruntime pesa)

        with _lock:
            if _detector is None:  # double-checked: uvicorn puede arrancar hilos
                _detector = ScrfdDetector(_model_path("det_10g.onnx"))
    return _detector


def embedder():
    global _embedder
    if _embedder is None:
        from app.ai.embedder import ArcFaceEmbedder

        with _lock:
            if _embedder is None:
                _embedder = ArcFaceEmbedder(_model_path("w600k_r50.onnx"))
    return _embedder


def gallery() -> FaceGallery:
    return _gallery


async def recargar_galeria(db: SQLModelAsyncSession) -> int:
    """Refresca la caché con los embeddings vigentes. Devuelve n. de alumnos."""
    rows = (await db.exec(select(FaceEmbedding).where(FaceEmbedding.is_current))).all()
    _gallery.reload(list(rows))
    return len(_gallery)


def vision_pipeline(cooldown_seconds: float = 30.0, threshold: float | None = None):
    """Pipeline listo para demo (sin classifier; el Bloque 6 lo inyectará).

    ``threshold=None`` usa el umbral de la configuración (RF-20; en el futuro
    se leerá de app_settings para que el admin lo ajuste en caliente, RF-34).
    """
    from app.ai.pipeline import VisionPipeline

    return VisionPipeline(
        detector(),
        embedder(),
        _gallery,
        threshold=threshold if threshold is not None else get_settings().FACE_MATCH_THRESHOLD,
        cooldown_seconds=cooldown_seconds,
    )
