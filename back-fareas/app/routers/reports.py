"""Reportes de asistencia — RF-16: descarga Excel/PDF con encabezado institucional.

Docentes: solo grupos PROPIOS (igual que RF-21). Admin: todo, con filtros
opcionales por curso. La consulta replica las columnas de v_today_attendance
pero sobre un RANGO de fechas (la vista solo cubre CURRENT_DATE).
"""
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import text as sql_text

from app.core.deps import DbSession, RequireRole
from app.services.exports import excel_asistencia, nombre_excel, nombre_pdf, pdf_asistencia
from app.tables import UserRole

router = APIRouter(tags=["reports"])

SQL_BASE = (
    "SELECT ar.id AS record_id, s.session_date AS att_date, st.id AS student_id, "
    "st.code AS student_code, st.full_name AS student_name, c.id AS course_id, "
    "c.code AS course_code, c.name AS course_name, cg.group_code, r.code AS room_code, "
    "ar.status::text AS status, ar.marked_at, ar.method, ar.similarity "
    "FROM attendance_record ar "
    "JOIN attendance_session s ON s.id = ar.session_id "
    "JOIN schedule_block  sb ON sb.id = s.block_id "
    "JOIN course_group    cg ON cg.id = sb.group_id "
    "JOIN course          c  ON c.id  = cg.course_id "
    "JOIN room            r  ON r.id  = cg.room_id "
    "JOIN app_user        st ON st.id = ar.student_id "
    "WHERE s.session_date BETWEEN :d1 AND :d2 "
    "AND cg.is_active "
)


async def _consultar(
    db, user, d1: date, d2: date, course_id: int | None,
) -> list[dict]:
    params: dict = {"d1": d1, "d2": d2}
    sql = SQL_BASE
    if user.role is UserRole.DOCENTE:
        sql += "AND cg.teacher_id = :docente "
        params["docente"] = user.id
    if course_id is not None:
        sql += "AND c.id = :curso "
        params["curso"] = course_id
    sql += "ORDER BY s.session_date DESC, sb.start_time, st.full_name LIMIT 5000"
    filas = (await db.exec(sql_text(sql).bindparams(**params))).all()
    return [
        {
            "record_id": f.record_id,
            "att_date": f.att_date.isoformat(),
            "student_id": f.student_id,
            "student_code": f.student_code,
            "student_name": f.student_name,
            "course_id": f.course_id,
            "course_code": f.course_code,
            "course_name": f.course_name,
            "group_code": f.group_code,
            "room_code": f.room_code,
            "status": f.status,
            "marked_at": f.marked_at.isoformat(timespec="seconds") if f.marked_at else None,
            "method": f.method,
            "similarity": float(f.similarity) if f.similarity is not None else None,
        }
        for f in filas
    ]


def _rango(desde: date | None, hasta: date | None) -> tuple[date, date]:
    hoy = date.today()
    d2 = hasta or hoy
    d1 = desde or (d2 - timedelta(days=30))  # default: último mes
    return d1, d2


def _respuesta(contenido: bytes, filename: str, media_type: str) -> StreamingResponse:
    return StreamingResponse(
        iter([contenido]),
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/reports/attendance.xlsx")
async def reporte_excel(
    db: DbSession,
    user: RequireRole(UserRole.ADMIN, UserRole.DOCENTE),
    desde: date | None = Query(None, description="Default: hasta - 30 días"),
    hasta: date | None = Query(None),
    course_id: int | None = Query(None),
) -> StreamingResponse:
    """RF-16: Excel con la asistencia del rango (encabezado institucional)."""
    d1, d2 = _rango(desde, hasta)
    filas = await _consultar(db, user, d1, d2, course_id)
    titulo = f"del {d1:%d/%m/%Y} al {d2:%d/%m/%Y}"
    return _respuesta(
        excel_asistencia(filas, titulo_periodo=titulo),
        nombre_excel(d1, d2, datetime.now()),
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@router.get("/reports/attendance.pdf")
async def reporte_pdf(
    db: DbSession,
    user: RequireRole(UserRole.ADMIN, UserRole.DOCENTE),
    desde: date | None = Query(None, description="Default: hasta - 30 días"),
    hasta: date | None = Query(None),
    course_id: int | None = Query(None),
) -> StreamingResponse:
    """RF-16: PDF horizontal con la asistencia del rango."""
    d1, d2 = _rango(desde, hasta)
    filas = await _consultar(db, user, d1, d2, course_id)
    titulo = f"del {d1:%d/%m/%Y} al {d2:%d/%m/%Y}"
    return _respuesta(
        pdf_asistencia(filas, titulo_periodo=titulo),
        nombre_pdf(d1, d2, datetime.now()),
        "application/pdf",
    )
