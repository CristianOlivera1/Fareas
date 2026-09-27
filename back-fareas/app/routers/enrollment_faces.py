"""Enrolamiento de rostros - RF-04 (solo admin escribe; docente consulta estado).

``POST /students/{id}/faces`` recibe 3-5 fotos en base64 (JSON). La lógica
(detección, consistencia, promedio, auditoría) vive en ``services/faces.py``.
"""
from fastapi import APIRouter, Request, status
from pydantic import BaseModel, Field
from sqlmodel import select

from app.core.deps import DbSession, RequireRole
from app.routers.catalog import _client_ip
from app.services.faces import enrolar
from app.tables import AppUser, FaceEmbedding, UserRole

router = APIRouter(tags=["enrollment"])


class EnrollmentIn(BaseModel):
    photos: list[str] = Field(
        min_length=3,
        max_length=5,
        description="Fotos JPEG/PNG del rostro codificadas en base64 (con o sin data-url).",
    )


@router.post("/students/{student_id}/faces", status_code=status.HTTP_201_CREATED)
async def enroll_student_faces(
    student_id: int,
    body: EnrollmentIn,
    request: Request,
    db: DbSession,
    admin: RequireRole(UserRole.ADMIN),
) -> dict:
    """RF-04: registra el rostro del alumno (3-5 fotos → embedding promedio)."""
    return await enrolar(db, admin, student_id, body.photos, ip=_client_ip(request))


@router.get("/students/{student_id}/faces")
async def enrollment_status(
    student_id: int,
    db: DbSession,
    _user: RequireRole(UserRole.ADMIN, UserRole.DOCENTE),
) -> dict:
    """Estado de enrolamiento del alumno (para el directorio del admin)."""
    student = await db.get(AppUser, student_id)
    if student is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Estudiante no encontrado")
    row = (
        await db.exec(
            select(FaceEmbedding)
            .where(FaceEmbedding.student_id == student_id, FaceEmbedding.is_current)  # type: ignore[arg-type]
        )
    ).first()
    return {
        "student_id": student_id,
        "enrolled": row is not None,
        "photo_url": row.photo_url if row else None,
        "source": row.source if row else None,
        "created_at": row.created_at.isoformat(timespec="seconds") if row and row.created_at else None,
    }
