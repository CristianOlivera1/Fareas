import base64
import binascii
import os

import cv2
import numpy as np
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from app.ai.detector import ScrfdDetector
from app.ai.embedder import ArcFaceEmbedder
from app.ai.runtime import detector as get_detector
from app.ai.runtime import embedder as get_embedder
from app.ai.runtime import recargar_galeria
from app.services import errors
from app.services.audit import audit
from app.services.storage import face_key, get_storage
from app.tables import AppUser, FaceEmbedding, UserRole

MIN_PHOTOS = 3
MAX_PHOTOS = 5
INTRA_MIN_SIMILARITY = 0.40
DETECT_THRESHOLD = 0.5


def _decode_photo(b64: str) -> np.ndarray:
    payload = b64.split(",", 1)[1] if b64.startswith("data:") else b64
    try:
        raw = base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise errors.DomainError("Una de las fotos no es base64 válido") from exc
    img = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise errors.DomainError("Una de las fotos no se pudo decodificar (¿JPEG/PNG?)")
    if img.shape[0] < 80 or img.shape[1] < 80:
        raise errors.DomainError("La foto es demasiado pequeña (mínimo 80x80)")
    return img

def _embedding_de_foto(det: ScrfdDetector, emb: ArcFaceEmbedder, img: np.ndarray, idx: int) -> np.ndarray:
    faces = det.detect(img, det_thresh=DETECT_THRESHOLD, max_faces=2)
    if not faces:
        raise errors.DomainError(f"Foto {idx}: no se detectó ningún rostro")
    if len(faces) > 1:
        raise errors.DomainError(f"Foto {idx}: se detectaron {len(faces)} rostros; debe ser solo el alumno")
    return emb.get(img, faces[0].kps)

def group_consistency(embeddings: list[np.ndarray]) -> tuple[float, int, float]:
    worst_similarity, worst_index = 1.0, 0
    for index, vector in enumerate(embeddings):
        others = np.mean([e for i, e in enumerate(embeddings) if i != index], axis=0)
        similarity = float(vector @ (others / np.linalg.norm(others)))
        if similarity < worst_similarity:
            worst_similarity, worst_index = similarity, index
    min_pair = min(
        float(embeddings[a] @ embeddings[b])
        for a in range(len(embeddings))
        for b in range(a + 1, len(embeddings))
    )
    return worst_similarity, worst_index, min_pair


async def enrolar(
    db: SQLModelAsyncSession,
    actor: AppUser,
    student_id: int,
    photos_b64: list[str],
    consent: bool = False,
    ip: str | None = None,
) -> dict:
    student = await db.get(AppUser, student_id)
    if student is None or student.role is not UserRole.ESTUDIANTE or not student.is_active:
        raise errors.NotFoundError("Estudiante no encontrado o inactivo")
    if not consent:
        raise errors.DomainError(
            "Se requiere el consentimiento expreso del estudiante para guardar datos biométricos (Ley 29733)"
        )

    if not MIN_PHOTOS <= len(photos_b64) <= MAX_PHOTOS:
        raise errors.DomainError(f"Se requieren entre {MIN_PHOTOS} y {MAX_PHOTOS} fotos (recibidas: {len(photos_b64)})")

    det, emb = get_detector(), get_embedder()
    embeddings = [_embedding_de_foto(det, emb, _decode_photo(p), i + 1) for i, p in enumerate(photos_b64)]

    group_sim, worst_index, min_pair = group_consistency(embeddings)
    if group_sim < INTRA_MIN_SIMILARITY:
        raise errors.DomainError(
            f"La foto {worst_index + 1} no coincide con las demás (similitud {group_sim:.2f} < {INTRA_MIN_SIMILARITY}); "
            "reemplázala por otra toma del mismo estudiante con buena luz y rostro de frente"
        )

    promedio = np.mean(embeddings, axis=0)
    promedio /= np.linalg.norm(promedio)

    storage = get_storage()
    photo_key = None
    try:
        primera = _decode_photo(photos_b64[0])
        fs = det.detect(primera, det_thresh=DETECT_THRESHOLD)
        if fs:
            ok, buf = cv2.imencode(".jpg", primera)
            if ok:
                photo_key = await storage.put(face_key(student_id), buf.tobytes(), "image/jpeg")
    except Exception:
        photo_key = None

    viejos = (await db.exec(select(FaceEmbedding).where(FaceEmbedding.student_id == student_id))).all()
    for viejo in viejos:
        viejo.is_current = False
        db.add(viejo)

    fila = FaceEmbedding(
        student_id=student_id,
        vector=[float(x) for x in promedio],
        photo_url=photo_key,
        source="promedio",
        is_current=True,
    )
    db.add(fila)
    await db.flush()
    if student.face_consent_at is None:
        from datetime import datetime

        student.face_consent_at = datetime.now()
        db.add(student)
        await audit(
            db, actor, action="consentimiento_facial", entity="app_user", entity_id=student_id,
            new_value={"face_consent_at": student.face_consent_at.isoformat(timespec="seconds")},
            ip_address=ip,
        )
    await audit(
        db, actor, action="enrolamiento_facial", entity="face_embedding", entity_id=fila.id,
        new_value={"student_id": student_id, "fotos": len(embeddings),
                   "consistencia_grupo": round(group_sim, 3), "consistencia_min_par": round(min_pair, 3),
                   "photo_key": photo_key},
        ip_address=ip,
    )
    await db.commit()
    await db.refresh(fila)

    await recargar_galeria(db)

    return {
        "student_id": student_id,
        "photos": len(embeddings),
        "min_pair_similarity": round(min_pair, 3),
        "min_group_similarity": round(group_sim, 3),
        "photo_url": await storage.url(photo_key),
        "embedding_id": fila.id,
    }

async def eliminar_rostro(
    db: SQLModelAsyncSession,
    actor: AppUser,
    student_id: int,
    ip: str | None = None,
) -> dict:
    student = await db.get(AppUser, student_id)
    if student is None or student.role is not UserRole.ESTUDIANTE:
        raise errors.NotFoundError("Estudiante no encontrado")

    storage = get_storage()
    filas = (
        await db.exec(select(FaceEmbedding).where(FaceEmbedding.student_id == student_id))
    ).all()
    for fila in filas:
        if fila.photo_url and fila.photo_url.startswith("storage/"):
            try:
                os.remove(fila.photo_url)
            except OSError:
                pass
        elif fila.photo_url:
            try:
                await storage.delete(fila.photo_url)
            except Exception:
                pass
        await db.delete(fila)

    tenia_consentimiento = student.face_consent_at is not None
    student.face_consent_at = None
    db.add(student)
    await audit(
        db, actor, action="rostro_eliminado", entity="app_user", entity_id=student_id,
        old_value={"embeddings": len(filas), "tenia_consentimiento": tenia_consentimiento},
        ip_address=ip,
    )
    await db.commit()
    await recargar_galeria(db)
    return {"student_id": student_id, "deleted": len(filas)}
