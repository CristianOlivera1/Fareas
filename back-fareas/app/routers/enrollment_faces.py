from fastapi import APIRouter, Request, status
from pydantic import BaseModel, Field
from sqlmodel import select

from app.core.deps import DbSession, RequireRole
from app.routers.catalog import _client_ip
from app.services.faces import eliminar_rostro, enrolar
from app.tables import AppUser, FaceEmbedding, UserRole

router = APIRouter(tags=["enrollment"])


class EnrollmentIn(BaseModel):
    photos: list[str] = Field(
        min_length=3,
        max_length=5,
        description="Fotos JPEG/PNG del rostro codificadas en base64 (con o sin data-url).",
    )
    consent: bool = Field(
        default=False,
        description="R13 (Ley 29733): consentimiento expreso del estudiante. Obligatorio en true.",
    )

@router.post("/students/{student_id}/faces", status_code=status.HTTP_201_CREATED)
async def enroll_student_faces(
    student_id: int,
    body: EnrollmentIn,
    request: Request,
    db: DbSession,
    admin: RequireRole(UserRole.ADMIN),
) -> dict:
    return await enrolar(db, admin, student_id, body.photos, consent=body.consent, ip=_client_ip(request))

@router.delete("/students/{student_id}/faces")
async def delete_student_faces(
    student_id: int,
    request: Request,
    db: DbSession,
    admin: RequireRole(UserRole.ADMIN),
) -> dict:
    return await eliminar_rostro(db, admin, student_id, ip=_client_ip(request))

@router.get("/students/{student_id}/faces")
async def enrollment_status(
    student_id: int,
    db: DbSession,
    _user: RequireRole(UserRole.ADMIN, UserRole.DOCENTE),
) -> dict:
    student = await db.get(AppUser, student_id)
    if student is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Estudiante no encontrado")
    row = (
        await db.exec(
            select(FaceEmbedding)
            .where(FaceEmbedding.student_id == student_id, FaceEmbedding.is_current)
        )
    ).first()
    return {
        "student_id": student_id,
        "enrolled": row is not None,
        "photo_url": row.photo_url if row else None,
        "source": row.source if row else None,
        "created_at": row.created_at.isoformat(timespec="seconds") if row and row.created_at else None,
    }
