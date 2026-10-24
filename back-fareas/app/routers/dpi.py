from fastapi import APIRouter, HTTPException, Query
from sqlmodel import select

from app.core.deps import DbSession, RequireRole
from app.services.dpi import nivel_de, resumen_alumno
from app.services.settings import get_settings_row
from app.tables import AppUser, CourseGroup, Enrollment, UserRole

router = APIRouter(tags=["dpi"])

TEACHER_SCOPE = (
    " AND EXISTS (SELECT 1 FROM enrollment e JOIN course_group cg ON cg.id = e.group_id "
    "WHERE e.student_id = v.student_id AND cg.course_id = v.course_id "
    "AND cg.semester_label = v.semester_label AND cg.teacher_id = :docente "
    "AND e.withdrawn_at IS NULL)"
)


@router.get("/dpi/at-risk")
async def dpi_at_risk(
    db: DbSession,
    user: RequireRole(UserRole.ADMIN, UserRole.DOCENTE),
    level: str | None = Query(None, pattern="^(alerta|limite)$"),
    course_id: int | None = None,
) -> list[dict]:
    from sqlalchemy import text as sql_text

    cfg = await get_settings_row(db)
    nivel_filtro = level or "alerta"
    sql = (
        "SELECT v.student_id, v.course_id, v.course_code, v.course_name, "
        "v.sessions_held, v.absences, v.justified_absences, v.lates, "
        "v.absence_percent, u.full_name, u.code AS student_code "
        "FROM v_student_dpi v JOIN app_user u ON u.id = v.student_id "
        "WHERE 1=1"
    )
    params: dict = {}
    if nivel_filtro == "limite":
        sql += " AND v.absence_percent > :limite"
        params["limite"] = float(cfg.dpi_limit_percent)
    else:
        sql += " AND v.absence_percent >= :alerta AND v.absence_percent <= :limite"
        params["alerta"] = float(cfg.dpi_alert_percent)
        params["limite"] = float(cfg.dpi_limit_percent)
    if user.role is UserRole.DOCENTE:
        sql += TEACHER_SCOPE
        params["docente"] = user.id
    if course_id is not None:
        sql += " AND v.course_id = :curso"
        params["curso"] = course_id
    sql += " ORDER BY v.absence_percent DESC LIMIT 500"
    filas = (await db.exec(sql_text(sql).bindparams(**params))).all()
    return [
        {
            "student_id": f.student_id,
            "student_code": f.student_code,
            "student_name": f.full_name,
            "course_id": f.course_id,
            "course_code": f.course_code,
            "course_name": f.course_name,
            "sessions_held": int(f.sessions_held),
            "absences": int(f.absences),
            "justified_absences": int(f.justified_absences),
            "lates": int(f.lates),
            "absence_percent": float(f.absence_percent),
            "nivel": nivel_de(float(f.absence_percent), cfg),
        }
        for f in filas
    ]

@router.get("/students/{student_id}/dpi")
async def student_dpi(
    student_id: int,
    db: DbSession,
    user: RequireRole(UserRole.ADMIN, UserRole.DOCENTE),
) -> list[dict]:
    student = await db.get(AppUser, student_id)
    if student is None or student.role is not UserRole.ESTUDIANTE:
        raise HTTPException(status_code=404, detail="Estudiante no encontrado")
    if user.role is UserRole.DOCENTE:
        propio = (
            await db.exec(
                select(Enrollment.id)
                .join(CourseGroup, CourseGroup.id == Enrollment.group_id)
                .where(
                    Enrollment.student_id == student_id,
                    Enrollment.withdrawn_at.is_(None),
                    CourseGroup.teacher_id == user.id,
                )
                .limit(1)
            )
        ).first()
        if propio is None:
            raise HTTPException(status_code=403, detail="El alumno no está matriculado en tus grupos")
    return await resumen_alumno(db, student_id)
