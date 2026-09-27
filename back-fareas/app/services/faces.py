"""Enrolamiento biométrico - RF-04: 3-5 fotos del rostro → embedding promedio.

Reglas implementadas:
- Solo estudiantes activos se enrolan.
- Entre 3 y 5 fotos; cada foto debe contener EXACTAMENTE un rostro detectable.
- Consistencia intra-alumno: la similitud mínima por pares entre fotos debe
  superar ``INTRA_MIN_SIMILARITY``; si no, probablemente son personas distintas
  o poses extremas y se rechaza el lote (422).
- El vector guardado es el PROMEDIO L2-normalizado de los embeddings
  (fuente 'promedio'; ``is_current=TRUE``). La validación empírica del bloque
  mostró que el promedio multi-pose identifica 20/22 frames de un video de
  prueba, contra 4/22 usando una sola foto frontal.
- La foto portada se guarda en ``storage/`` (prod: Cloudflare R2, §7 del plan).
- Todo queda en audit_log (RF-32) dentro de la transacción.
"""
import base64
import binascii
import os
import uuid

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
from app.tables import AppUser, FaceEmbedding, UserRole

MIN_PHOTOS = 3
MAX_PHOTOS = 5
INTRA_MIN_SIMILARITY = 0.55  # entre fotos del MISMO alumno (mínimo por pares)
DETECT_THRESHOLD = 0.5  # det_thresh para enrolar (estricto)


def _decode_photo(b64: str) -> np.ndarray:
    """Base64 (con o sin data-url) → frame BGR. Lanza DomainError si es inválida."""
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
    """Embedding de UNA foto: exige exactamente un rostro bien detectado."""
    faces = det.detect(img, det_thresh=DETECT_THRESHOLD, max_faces=2)
    if not faces:
        raise errors.DomainError(f"Foto {idx}: no se detectó ningún rostro")
    if len(faces) > 1:
        raise errors.DomainError(f"Foto {idx}: se detectaron {len(faces)} rostros; debe ser solo el alumno")
    return emb.get(img, faces[0].kps)


async def enrolar(
    db: SQLModelAsyncSession,
    actor: AppUser,
    student_id: int,
    photos_b64: list[str],
    ip: str | None = None,
) -> dict:
    """RF-04 completo: valida, promedia, guarda y audita. Devuelve resumen."""
    student = await db.get(AppUser, student_id)
    if student is None or student.role is not UserRole.ESTUDIANTE or not student.is_active:
        raise errors.NotFoundError("Estudiante no encontrado o inactivo")

    if not MIN_PHOTOS <= len(photos_b64) <= MAX_PHOTOS:
        raise errors.DomainError(f"Se requieren entre {MIN_PHOTOS} y {MAX_PHOTOS} fotos (recibidas: {len(photos_b64)})")

    det, emb = get_detector(), get_embedder()
    embeddings = [_embedding_de_foto(det, emb, _decode_photo(p), i + 1) for i, p in enumerate(photos_b64)]

    # Consistencia intra-alumno: todas las fotos deben ser de la misma persona.
    min_sim = 1.0
    for a in range(len(embeddings)):
        for b in range(a + 1, len(embeddings)):
            min_sim = min(min_sim, float(embeddings[a] @ embeddings[b]))
    if min_sim < INTRA_MIN_SIMILARITY:
        raise errors.DomainError(
            f"Las fotos no parecen ser de la misma persona (consistencia mínima {min_sim:.2f} < {INTRA_MIN_SIMILARITY}); "
            "repite el enrolamiento con mejores tomas"
        )

    promedio = np.mean(embeddings, axis=0)
    promedio /= np.linalg.norm(promedio)

    # La portada (primer foto) se guarda en storage/ para el directorio de estudiantes.
    photo_url = None
    try:
        primera = _decode_photo(photos_b64[0])
        fs = det.detect(primera, det_thresh=DETECT_THRESHOLD)
        if fs:
            os.makedirs("storage", exist_ok=True)
            fname = f"student_{student_id}_{uuid.uuid4().hex[:8]}.jpg"
            cv2.imwrite(os.path.join("storage", fname), primera)
            photo_url = f"storage/{fname}"
    except Exception:  # la portada es best-effort; el embedding es lo crítico
        photo_url = None

    # Reemplazo: el embedding anterior deja de ser vigente (historial completo).
    viejos = (await db.exec(select(FaceEmbedding).where(FaceEmbedding.student_id == student_id))).all()
    for viejo in viejos:
        viejo.is_current = False
        db.add(viejo)

    fila = FaceEmbedding(
        student_id=student_id,
        vector=[float(x) for x in promedio],
        photo_url=photo_url,
        source="promedio",
        is_current=True,
    )
    db.add(fila)
    await db.flush()
    await audit(
        db, actor, action="enrolamiento_facial", entity="face_embedding", entity_id=fila.id,
        new_value={"student_id": student_id, "fotos": len(embeddings),
                   "consistencia_min": round(min_sim, 3), "photo_url": photo_url},
        ip_address=ip,
    )
    await db.commit()
    await db.refresh(fila)

    # La galería en memoria se refresca al instante: la puerta reconoce al
    # alumno en el siguiente frame sin reiniciar el proceso.
    await recargar_galeria(db)

    return {
        "student_id": student_id,
        "photos": len(embeddings),
        "min_pair_similarity": round(min_sim, 3),
        "photo_url": photo_url,
        "embedding_id": fila.id,
    }
