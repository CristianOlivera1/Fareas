from datetime import date, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import text as sql_text
from sqlmodel import select

from app.core.deps import DbSession, RequireRole
from app.routers.courses import consultar_horario
from app.services.report_data import CATALOGO, CONSTRUCTORES, ESTADOS, Filtros, construir_reporte
from app.services.report_render import FORMATOS, nombre_archivo, renderizar
from app.services.schedule_export import Opciones, exportar_horario
from app.services.settings import semestre_vigente
from app.services.exports import (
    excel_asistencia,
    excel_matriz_grupo,
    excel_riesgo_dpi,
    nombre_excel,
    nombre_matriz,
    nombre_pdf,
    nombre_riesgo,
    pdf_asistencia,
)
from app.tables import (
    AppUser,
    AttendanceRecord,
    AttendanceSession,
    Course,
    CourseGroup,
    Enrollment,
    ScheduleBlock,
    UserRole,
)

router = APIRouter(tags=["reports"])

SQL_BASE = (
    "SELECT ar.id AS record_id, s.session_date AS att_date, st.id AS student_id, "
    "st.code AS student_code, st.full_name AS student_name, c.id AS course_id, "
    "c.code AS course_code, c.name AS course_name, cg.group_code, r.code AS room_code, "
    "ar.status::text AS status, ar.marked_at, ar.method, ar.similarity, ar.is_justified "
    "FROM attendance_record ar "
    "JOIN attendance_session s ON s.id = ar.session_id "
    "JOIN schedule_block  sb ON sb.id = s.block_id "
    "JOIN course_group    cg ON cg.id = sb.group_id "
    "JOIN course          c  ON c.id  = cg.course_id "
    "LEFT JOIN room       r  ON r.id  = sb.room_id "
    "JOIN app_user        st ON st.id = ar.student_id "
    "WHERE s.session_date BETWEEN :d1 AND :d2 "
    "AND cg.is_active "
    "AND s.status <> 'cancelada' AND s.needs_review = FALSE "
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
            "is_justified": bool(f.is_justified),
        }
        for f in filas
    ]

def _rango(desde: date | None, hasta: date | None) -> tuple[date, date]:
    hoy = date.today()
    d2 = hasta or hoy
    d1 = desde or (d2 - timedelta(days=30))
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
    d1, d2 = _rango(desde, hasta)
    filas = await _consultar(db, user, d1, d2, course_id)
    titulo = f"del {d1:%d/%m/%Y} al {d2:%d/%m/%Y}"
    return _respuesta(
        pdf_asistencia(filas, titulo_periodo=titulo),
        nombre_pdf(d1, d2, datetime.now()),
        "application/pdf",
    )

async def _grupo_y_curso(db, group_id: int) -> tuple[CourseGroup, Course]:
    grupo = await db.get(CourseGroup, group_id)
    if grupo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Grupo no encontrado")
    curso = await db.get(Course, grupo.course_id)
    if curso is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Curso no encontrado")
    return grupo, curso

def _exige_docente_propio(user, grupo: CourseGroup) -> None:
    if user.role is UserRole.DOCENTE and grupo.teacher_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No es tu grupo")

@router.get("/reports/group-matrix.xlsx")
async def reporte_matriz_grupo(
    db: DbSession,
    user: RequireRole(UserRole.ADMIN, UserRole.DOCENTE),
    group_id: int = Query(..., description="Grupo a exportar"),
) -> StreamingResponse:
    grupo, curso = await _grupo_y_curso(db, group_id)
    _exige_docente_propio(user, grupo)

    sesiones = (
        await db.exec(
            select(AttendanceSession, ScheduleBlock)
            .join(ScheduleBlock, ScheduleBlock.id == AttendanceSession.block_id)
            .where(
                ScheduleBlock.group_id == group_id,
                AttendanceSession.status == "cerrada",
                AttendanceSession.needs_review.is_(False),
            )
            .order_by(AttendanceSession.session_date, ScheduleBlock.start_time)
        )
    ).all()
    fechas: list[tuple[int, str]] = [
        (ses.id, f"{ses.session_date:%d/%m} {bloque.start_time:%H:%M}")
        for ses, bloque in sesiones
    ]

    alumnos = (
        await db.exec(
            select(AppUser)
            .join(Enrollment, Enrollment.student_id == AppUser.id)
            .where(
                Enrollment.group_id == group_id,
                Enrollment.withdrawn_at.is_(None),
            )
            .order_by(AppUser.full_name)
        )
    ).all()

    celdas: dict[tuple[int, int], str] = {}
    if sesiones:
        ids = [ses.id for ses, _b in sesiones]
        registros = (
            await db.exec(
                select(AttendanceRecord).where(AttendanceRecord.session_id.in_(ids))
            )
        ).all()
        for r in registros:
            estado = r.status.value if hasattr(r.status, "value") else str(r.status)
            marca = {"asistio": "A", "tardanza": "T"}.get(estado)
            if estado == "falta":
                marca = "FJ" if r.is_justified else "F"
            celdas[(r.student_id, r.session_id)] = marca or "—"

    etiquetas = [etiqueta for _sid, etiqueta in fechas]
    filas_out = [
        {
            "student_name": alumno.full_name,
            "student_code": alumno.code,
            "celdas": {
                etiquetas[i]: celdas.get((alumno.id, sid), "—")
                for i, (sid, _e) in enumerate(fechas)
            },
        }
        for alumno in alumnos
    ]
    return _respuesta(
        excel_matriz_grupo(filas_out, etiquetas,
                           titulo_periodo=f"{curso.code} - {curso.name} (Grupo {grupo.group_code})"),
        nombre_matriz(grupo.group_code, curso.code, datetime.now()),
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

@router.get("/reports/dpi-risk.xlsx")
async def reporte_riesgo_dpi(
    db: DbSession,
    user: RequireRole(UserRole.ADMIN, UserRole.DOCENTE),
    course_id: int | None = Query(None, description="Solo un curso (opcional)"),
) -> StreamingResponse:
    cfg_sql = "SELECT dpi_alert_percent FROM app_settings WHERE id = 1"
    alerta = (await db.exec(sql_text(cfg_sql))).scalar_one()
    sql = (
        "SELECT v.student_id, v.course_id, v.course_code, v.course_name, v.sessions_held, "
        "v.absences, v.justified_absences, v.lates, v.absence_percent, v.semester_label, "
        "u.full_name AS student_name, u.code AS student_code "
        "FROM v_student_dpi v JOIN app_user u ON u.id = v.student_id "
        "WHERE v.absence_percent >= :alerta"
    )
    params: dict = {"alerta": float(alerta)}
    if course_id is not None:
        sql += " AND v.course_id = :curso"
        params["curso"] = course_id
    if user.role is UserRole.DOCENTE:
        sql += (" AND v.course_id IN (SELECT cg.course_id FROM course_group cg "
                "WHERE cg.teacher_id = :docente AND cg.is_active)")
        params["docente"] = user.id
    sql += " ORDER BY v.absence_percent DESC, u.full_name LIMIT 5000"
    filas_sql = (await db.exec(sql_text(sql).bindparams(**params))).all()

    limite = (await db.exec(sql_text(
        "SELECT dpi_limit_percent FROM app_settings WHERE id = 1"))).scalar_one()
    limite_f = float(limite)

    from app.services.dpi import sesiones_planificadas
    from app.services.settings import get_settings_row

    cfg = await get_settings_row(db)
    out = []
    for f in filas_sql:
        percent = float(f.absence_percent)
        plan = await sesiones_planificadas(db, int(f.student_id), int(f.course_id), cfg)
        permitidas = int(plan * limite_f / 100) if plan is not None else None
        out.append({
            "student_name": f.student_name,
            "student_code": f.student_code,
            "course_code": f.course_code,
            "course_name": f.course_name,
            "sessions_held": int(f.sessions_held),
            "absences": int(f.absences),
            "justified_absences": int(f.justified_absences),
            "lates": int(f.lates),
            "absence_percent": percent,
            "nivel": "limite" if percent > limite_f else "alerta",
            "faltas_permitidas": permitidas,
            "faltas_restantes": max(0, permitidas - int(f.absences)) if permitidas is not None else None,
        })
    return _respuesta(
        excel_riesgo_dpi(out, titulo_periodo=f"Nivel alerta ≥ {float(alerta):.0f}% · límite > {limite_f:.0f}%"),
        nombre_riesgo(datetime.now()),
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@router.get("/schedule/export")
async def exportar_horario_general(
    db: DbSession,
    _user: RequireRole(UserRole.ADMIN, UserRole.DOCENTE),
    format: Literal["pdf", "xlsx", "png"] = Query("pdf", description="Formato del archivo"),
    semester: str | None = Query(None, max_length=40, description="Default: semestre vigente"),
    cycle: int | None = Query(None, ge=1, le=10, description="Un ciclo; sin valor exporta todos"),
    course_id: int | None = None,
    teacher_id: int | None = None,
    room_id: int | None = None,
    show_teacher: bool = Query(True, description="Incluye el docente en cada celda"),
    show_room: bool = Query(True, description="Incluye el aula en cada celda"),
) -> StreamingResponse:
    semestre = semester or await semestre_vigente(db)
    filas = await consultar_horario(db, semestre, cycle, course_id, teacher_id, room_id)
    if not filas:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No hay clases para exportar con esos filtros"
        )
    contenido, media_type, nombre = exportar_horario(
        format, [fila.model_dump() for fila in filas], semestre, cycle,
        Opciones(docente=show_teacher, aula=show_room),
    )
    return _respuesta(contenido, nombre, media_type)


def _filtros_reporte(
    desde: date | None, hasta: date | None, cycle: int | None, course_id: int | None,
    group_id: int | None, teacher_id: int | None, room_id: int | None, status_csv: str | None,
    q: str | None, only_risk: bool,
) -> Filtros:
    if desde and hasta and desde > hasta:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="La fecha inicial no puede ser posterior a la final",
        )
    estados = [e.strip() for e in (status_csv or "").split(",") if e.strip()]
    invalidos = [e for e in estados if e not in ESTADOS]
    if invalidos:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Estado no válido: {', '.join(invalidos)}",
        )
    return Filtros(
        desde=desde, hasta=hasta, cycle=cycle, course_id=course_id, group_id=group_id,
        teacher_id=teacher_id, room_id=room_id, estados=estados, q=q, solo_riesgo=only_risk,
    )


def _exige_reporte(kind: str) -> None:
    if kind not in CONSTRUCTORES:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reporte no encontrado")


@router.get("/reports/catalog")
async def catalogo_reportes(_user: RequireRole(UserRole.ADMIN, UserRole.DOCENTE)) -> list[dict]:
    return [
        {
            "key": r.clave, "title": r.titulo, "description": r.descripcion, "icon": r.icono,
            "formats": list(r.formatos), "filters": list(r.filtros),
        }
        for r in CATALOGO
    ]


@router.get("/reports/preview")
async def vista_previa_reporte(
    db: DbSession,
    user: RequireRole(UserRole.ADMIN, UserRole.DOCENTE),
    kind: str = Query(..., description="Reporte del catálogo"),
    desde: date | None = None,
    hasta: date | None = None,
    cycle: int | None = Query(None, ge=1, le=10),
    course_id: int | None = None,
    group_id: int | None = None,
    teacher_id: int | None = None,
    room_id: int | None = None,
    status_filter: str | None = Query(None, alias="status", description="Estados separados por coma"),
    q: str | None = Query(None, max_length=80),
    only_risk: bool = False,
    limit: int = Query(8, ge=1, le=50),
) -> dict:
    _exige_reporte(kind)
    filtros = _filtros_reporte(
        desde, hasta, cycle, course_id, group_id, teacher_id, room_id, status_filter, q, only_risk
    )
    tabla = await construir_reporte(db, user, kind, filtros)
    return {
        "key": kind,
        "title": tabla.titulo,
        "description": tabla.descripcion,
        "filters": [{"label": k, "value": v} for k, v in tabla.filtros],
        "indicators": [{"label": i.etiqueta, "value": i.valor, "tone": i.tono} for i in tabla.indicadores],
        "columns": [{"key": c.clave, "title": c.titulo, "align": c.alinear} for c in tabla.columnas],
        "rows": [[{"value": c.valor, "tone": c.tono} for c in fila] for fila in tabla.filas[:limit]],
        "total": len(tabla.filas),
        "truncated": tabla.truncada,
    }


@router.get("/reports/export")
async def exportar_reporte(
    db: DbSession,
    user: RequireRole(UserRole.ADMIN, UserRole.DOCENTE),
    kind: str = Query(..., description="Reporte del catálogo"),
    format: Literal["pdf", "xlsx", "csv"] = Query("pdf"),
    desde: date | None = None,
    hasta: date | None = None,
    cycle: int | None = Query(None, ge=1, le=10),
    course_id: int | None = None,
    group_id: int | None = None,
    teacher_id: int | None = None,
    room_id: int | None = None,
    status_filter: str | None = Query(None, alias="status", description="Estados separados por coma"),
    q: str | None = Query(None, max_length=80),
    only_risk: bool = False,
) -> StreamingResponse:
    _exige_reporte(kind)
    filtros = _filtros_reporte(
        desde, hasta, cycle, course_id, group_id, teacher_id, room_id, status_filter, q, only_risk
    )
    tabla = await construir_reporte(db, user, kind, filtros)
    return _respuesta(
        renderizar(tabla, format), nombre_archivo(tabla, format, datetime.now()), FORMATOS[format][0]
    )
