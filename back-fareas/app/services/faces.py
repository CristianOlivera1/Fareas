import base64
import binascii
import contextlib
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
DUPLICATE_SIMILARITY = 0.60
MIN_FACE_PX = 90
MIN_DETECT_SCORE = 0.6
MAX_YAW_RATIO = 0.35
MAX_ROLL_DEG = 20.0
MIN_SHARPNESS = 25.0


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

def _nitidez(img: np.ndarray, box: np.ndarray) -> float:
    height, width = img.shape[:2]
    x1, y1 = max(0, int(box[0])), max(0, int(box[1]))
    x2, y2 = min(width, int(box[2])), min(height, int(box[3]))
    if x2 - x1 < 8 or y2 - y1 < 8:
        return 0.0
    gris = cv2.cvtColor(img[y1:y2, x1:x2], cv2.COLOR_BGR2GRAY)
    gris = cv2.resize(gris, (112, 112), interpolation=cv2.INTER_AREA)
    return float(cv2.Laplacian(gris, cv2.CV_64F).var())


def validar_calidad(img: np.ndarray, face, idx: int) -> None:
    ancho = float(face.box[2] - face.box[0])
    alto = float(face.box[3] - face.box[1])
    if min(ancho, alto) < MIN_FACE_PX:
        raise errors.DomainError(
            f"Foto {idx}: el rostro es muy pequeño ({int(min(ancho, alto))} px, mínimo {MIN_FACE_PX}); "
            "acércate a la cámara"
        )
    if face.score < MIN_DETECT_SCORE:
        raise errors.DomainError(f"Foto {idx}: el rostro no se ve con claridad; mejora la iluminación")
    ojo_izq, ojo_der, nariz = face.kps[0], face.kps[1], face.kps[2]
    distancia = float(np.linalg.norm(ojo_der - ojo_izq))
    if distancia < 1.0:
        raise errors.DomainError(f"Foto {idx}: no se distinguen los ojos; mira de frente a la cámara")
    desvio = abs(float(nariz[0] - (ojo_izq[0] + ojo_der[0]) / 2)) / distancia
    if desvio > MAX_YAW_RATIO:
        raise errors.DomainError(f"Foto {idx}: mira de frente a la cámara, sin girar la cabeza")
    inclinacion = abs(float(np.degrees(np.arctan2(ojo_der[1] - ojo_izq[1], ojo_der[0] - ojo_izq[0]))))
    if inclinacion > MAX_ROLL_DEG:
        raise errors.DomainError(f"Foto {idx}: mantén la cabeza derecha")
    if _nitidez(img, face.box) < MIN_SHARPNESS:
        raise errors.DomainError(f"Foto {idx}: la foto está borrosa; mantén firme la cámara y mejora la luz")


def _embedding_de_foto(det: ScrfdDetector, emb: ArcFaceEmbedder, img: np.ndarray, idx: int) -> np.ndarray:
    faces = det.detect(img, det_thresh=DETECT_THRESHOLD, max_faces=2)
    if not faces:
        raise errors.DomainError(f"Foto {idx}: no se detectó ningún rostro")
    if len(faces) > 1:
        raise errors.DomainError(f"Foto {idx}: se detectaron {len(faces)} rostros; debe ser solo el alumno")
    validar_calidad(img, faces[0], idx)
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


async def _rechazar_rostro_duplicado(db: SQLModelAsyncSession, student_id: int, vector: np.ndarray) -> None:
    from app.ai.recognizer import parse_pg_array

    filas = (
        await db.exec(
            select(FaceEmbedding.vector, AppUser.code, AppUser.full_name)
            .join(AppUser, AppUser.id == FaceEmbedding.student_id)
            .where(FaceEmbedding.student_id != student_id, FaceEmbedding.is_current, AppUser.is_active)
        )
    ).all()
    mejor: tuple[float, str, str] | None = None
    for crudo, codigo, nombre in filas:
        otro = parse_pg_array(crudo)
        if otro is None or otro.size != vector.size:
            continue
        similitud = float(vector @ otro)
        if similitud >= DUPLICATE_SIMILARITY and (mejor is None or similitud > mejor[0]):
            mejor = (similitud, codigo or "sin código", nombre)
    if mejor is not None:
        raise errors.ConflictError(
            f"Este rostro ya está enrolado en la cuenta de {mejor[2]} ({mejor[1]}), similitud {mejor[0]:.2f}. "
            "Si es la misma persona, elimina primero el rostro de esa cuenta; si no, repite las fotos con mejor luz y de frente"
        )


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

    await _rechazar_rostro_duplicado(db, student_id, promedio)

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
    replaced_photo_keys = [viejo.photo_url for viejo in viejos if viejo.photo_url]
    for viejo in viejos:
        await db.delete(viejo)

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

    for key in replaced_photo_keys:
        await _discard_photo(storage, key)

    await recargar_galeria(db)

    return {
        "student_id": student_id,
        "photos": len(embeddings),
        "min_pair_similarity": round(min_pair, 3),
        "min_group_similarity": round(group_sim, 3),
        "photo_url": await storage.url(photo_key),
        "embedding_id": fila.id,
    }

async def _discard_photo(storage, key: str) -> None:
    if key.startswith("storage/"):
        with contextlib.suppress(OSError):
            os.remove(key)
    with contextlib.suppress(Exception):
        await storage.delete(key)


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
        if fila.photo_url:
            await _discard_photo(storage, fila.photo_url)
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
