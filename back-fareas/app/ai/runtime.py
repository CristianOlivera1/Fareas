import os
import threading

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from app.ai.recognizer import FaceGallery
from app.core.config import get_settings
from app.tables import AppUser, FaceEmbedding

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
        from app.ai.detector import ScrfdDetector

        with _lock:
            if _detector is None:
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
    rows = (
        await db.exec(
            select(FaceEmbedding)
            .join(AppUser, AppUser.id == FaceEmbedding.student_id)
            .where(FaceEmbedding.is_current, AppUser.is_active)
        )
    ).all()
    _gallery.reload(list(rows))
    return len(_gallery)

def vision_pipeline(cooldown_seconds: float = 30.0, threshold: float | None = None):
    from app.ai.pipeline import VisionPipeline

    return VisionPipeline(
        detector(),
        embedder(),
        _gallery,
        threshold=threshold if threshold is not None else get_settings().FACE_MATCH_THRESHOLD,
        cooldown_seconds=cooldown_seconds,
        margin=get_settings().FACE_MATCH_MARGIN,
        confirm_frames=get_settings().FACE_CONFIRM_FRAMES,
        min_face_px=get_settings().FACE_MIN_SIZE_PX,
    )
