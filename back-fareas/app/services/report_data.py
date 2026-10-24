from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlalchemy import text as sql_text

from app.services.report_render import Celda, Columna, Indicador, Tabla
from app.tables import AppUser, Course, CourseGroup, Room, UserRole

LIMITE_DETALLE = 5000

ESTADOS = {
    "asistio": ("Asistió", "ar.status::text = 'asistio'", "ok"),
    "tardanza": ("Tardanza", "ar.status::text = 'tardanza'", "warn"),
    "falta": ("Falta", "(ar.status::text = 'falta' AND NOT ar.is_justified)", "bad"),
    "falta_justificada": (
        "Falta justificada", "(ar.status::text = 'falta' AND ar.is_justified)", "info",
    ),
}
ROMANOS = {1: "I", 2: "II", 3: "III", 4: "IV", 5: "V", 6: "VI", 7: "VII", 8: "VIII", 9: "IX", 10: "X"}

FROM_BASE = (
    "FROM attendance_record ar "
    "JOIN attendance_session s ON s.id = ar.session_id "
    "JOIN schedule_block sb ON sb.id = s.block_id "
    "JOIN course_group cg ON cg.id = sb.group_id "
    "JOIN course c ON c.id = cg.course_id "
    "LEFT JOIN room r ON r.id = sb.room_id "
    "LEFT JOIN app_user t ON t.id = cg.teacher_id "
    "JOIN app_user st ON st.id = ar.student_id "
    "WHERE s.session_date BETWEEN :d1 AND :d2 AND cg.is_active "
    "AND s.status <> 'cancelada' AND s.needs_review = FALSE "
)

SUMA_ESTADOS = (
    "COUNT(*) FILTER (WHERE ar.status::text = 'asistio') AS asistio, "
    "COUNT(*) FILTER (WHERE ar.status::text = 'tardanza') AS tardanza, "
    "COUNT(*) FILTER (WHERE ar.status::text = 'falta' AND NOT ar.is_justified) AS falta, "
    "COUNT(*) FILTER (WHERE ar.status::text = 'falta' AND ar.is_justified) AS justificada, "
    "COUNT(*) AS total "
)


@dataclass
class Filtros:
    desde: date | None = None
    hasta: date | None = None
    cycle: int | None = None
    course_id: int | None = None
    group_id: int | None = None
    teacher_id: int | None = None
    room_id: int | None = None
    estados: list[str] = field(default_factory=list)
    q: str | None = None
    solo_riesgo: bool = False

    def rango(self) -> tuple[date, date]:
        hasta = self.hasta or date.today()
        return self.desde or (hasta - timedelta(days=30)), hasta


@dataclass(frozen=True)
class Catalogo:
    clave: str
    titulo: str
    descripcion: str
    icono: str
    formatos: tuple[str, ...]
    filtros: tuple[str, ...]


CATALOGO = [
    Catalogo(
        "attendance", "Asistencia detallada",
        "Un registro por alumno y sesión: fecha, hora de marca, aula, estado y método.",
        "material-symbols:table-chart-outline", ("pdf", "xlsx", "csv"),
        ("periodo", "ciclo", "curso", "grupo", "docente", "aula", "estado", "alumno"),
    ),
    Catalogo(
        "course-summary", "Resumen por curso y grupo",
        "Totales de asistencia, tardanzas y faltas por grupo, con su porcentaje de asistencia.",
        "material-symbols:bar-chart-4-bars", ("pdf", "xlsx", "csv"),
        ("periodo", "ciclo", "curso", "grupo", "docente", "aula"),
    ),
    Catalogo(
        "student-summary", "Resumen por estudiante",
        "Situación de cada alumno por curso, con porcentaje de inasistencia y nivel de riesgo.",
        "material-symbols:person-search-outline", ("pdf", "xlsx", "csv"),
        ("periodo", "ciclo", "curso", "grupo", "docente", "alumno", "riesgo"),
    ),
    Catalogo(
        "dpi-risk", "Riesgo de inasistencia",
        "Alumnos en alerta o sobre el límite de faltas del periodo vigente, con las faltas que les quedan.",
        "material-symbols:warning-outline", ("pdf", "xlsx", "csv"),
        ("ciclo", "curso", "alumno"),
    ),
]


def _where(user, f: Filtros) -> tuple[str, dict]:
    d1, d2 = f.rango()
    sql, params = "", {"d1": d1, "d2": d2}
    if user.role is UserRole.DOCENTE:
        sql += "AND cg.teacher_id = :docente "
        params["docente"] = user.id
    elif f.teacher_id is not None:
        sql += "AND cg.teacher_id = :docente "
        params["docente"] = f.teacher_id
    for columna, valor, nombre in (
        ("c.cycle", f.cycle, "ciclo"), ("c.id", f.course_id, "curso"),
        ("cg.id", f.group_id, "grupo"), ("sb.room_id", f.room_id, "aula"),
    ):
        if valor is not None:
            sql += f"AND {columna} = :{nombre} "
            params[nombre] = valor
    if f.q and f.q.strip():
        sql += "AND (st.full_name ILIKE :q OR st.code ILIKE :q) "
        params["q"] = f"%{f.q.strip()}%"
    elegidos = [ESTADOS[e][1] for e in f.estados if e in ESTADOS]
    if elegidos:
        sql += "AND (" + " OR ".join(elegidos) + ") "
    return sql, params


async def _describir(db, user, f: Filtros) -> list[tuple[str, str]]:
    d1, d2 = f.rango()
    filtros = [("Periodo", f"{d1:%d/%m/%Y} al {d2:%d/%m/%Y}")]
    if f.cycle is not None:
        filtros.append(("Ciclo", ROMANOS.get(f.cycle, str(f.cycle))))
    if f.course_id is not None:
        curso = await db.get(Course, f.course_id)
        if curso:
            filtros.append(("Curso", f"{curso.code} · {curso.name}"))
    if f.group_id is not None:
        grupo = await db.get(CourseGroup, f.group_id)
        if grupo:
            filtros.append(("Grupo", grupo.group_code))
    if user.role is UserRole.DOCENTE:
        filtros.append(("Docente", user.full_name))
    elif f.teacher_id is not None:
        docente = await db.get(AppUser, f.teacher_id)
        if docente:
            filtros.append(("Docente", docente.full_name))
    if f.room_id is not None:
        aula = await db.get(Room, f.room_id)
        if aula:
            filtros.append(("Aula", aula.code))
    if f.estados:
        filtros.append(("Estado", ", ".join(ESTADOS[e][0] for e in f.estados if e in ESTADOS)))
    if f.q and f.q.strip():
        filtros.append(("Alumno", f.q.strip()))
    if f.solo_riesgo:
        filtros.append(("Riesgo", "Solo alumnos en alerta o límite"))
    return filtros


def _porcentaje(parte: int, total: int) -> float:
    return round(parte * 100 / total, 1) if total else 0.0


def _indicadores(asistio: int, tardanza: int, falta: int, justificada: int) -> list[Indicador]:
    total = asistio + tardanza + falta + justificada
    pct = _porcentaje(asistio + tardanza, total)
    return [
        Indicador("Registros", str(total), "muted"),
        Indicador("% de asistencia", f"{pct}%", "ok" if pct >= 80 else "warn" if pct >= 70 else "bad"),
        Indicador("Asistencias", str(asistio), "ok"),
        Indicador("Tardanzas", str(tardanza), "warn"),
        Indicador("Faltas", str(falta), "bad"),
        Indicador("Justificadas", str(justificada), "info"),
    ]


async def _niveles(db) -> tuple[float, float]:
    fila = (await db.exec(sql_text(
        "SELECT dpi_alert_percent, dpi_limit_percent FROM app_settings WHERE id = 1"
    ))).one()
    return float(fila.dpi_alert_percent), float(fila.dpi_limit_percent)


def _nivel(pct_inasistencia: float, alerta: float, limite: float) -> tuple[str, str]:
    if pct_inasistencia > limite:
        return "Límite", "bad"
    if pct_inasistencia >= alerta:
        return "Alerta", "warn"
    return "Normal", "ok"


async def _detalle(db, user, f: Filtros) -> Tabla:
    donde, params = _where(user, f)
    sql = (
        "SELECT s.session_date AS fecha, ar.marked_at, st.full_name AS alumno, st.code AS codigo, "
        "c.code AS curso_codigo, c.name AS curso, cg.group_code AS grupo, r.code AS aula, "
        "t.full_name AS docente, ar.status::text AS estado, ar.is_justified, ar.method, "
        "ar.similarity " + FROM_BASE + donde +
        f"ORDER BY s.session_date DESC, sb.start_time, st.full_name LIMIT {LIMITE_DETALLE + 1}"
    )
    registros = (await db.exec(sql_text(sql).bindparams(**params))).all()
    truncada = len(registros) > LIMITE_DETALLE
    registros = registros[:LIMITE_DETALLE]
    filas = []
    conteo = {"asistio": 0, "tardanza": 0, "falta": 0, "falta_justificada": 0}
    for r in registros:
        clave = "falta_justificada" if r.estado == "falta" and r.is_justified else r.estado
        if clave in conteo:
            conteo[clave] += 1
        etiqueta, _, tono = ESTADOS.get(clave, (r.estado, "", "muted"))
        filas.append([
            Celda(f"{r.fecha:%d/%m/%Y}"),
            Celda(f"{r.marked_at:%H:%M}" if r.marked_at else "—", None),
            Celda(r.alumno), Celda(r.codigo or "—"),
            Celda(f"{r.curso_codigo} · {r.curso}"), Celda(r.grupo), Celda(r.aula or "—"),
            Celda(r.docente or "—"), Celda(etiqueta, tono), Celda(r.method or "—"),
            Celda(round(float(r.similarity) * 100, 1) if r.similarity is not None else "—"),
        ])
    columnas = [
        Columna("fecha", "Fecha", 1.0, "center"), Columna("hora", "Hora", 0.7, "center"),
        Columna("alumno", "Estudiante", 2.4), Columna("codigo", "Código", 1.0),
        Columna("curso", "Curso", 2.6), Columna("grupo", "Grupo", 0.6, "center"),
        Columna("aula", "Aula", 0.9, "center"), Columna("docente", "Docente", 2.0),
        Columna("estado", "Estado", 1.3, "center"), Columna("metodo", "Método", 0.9, "center"),
        Columna("similitud", "Similitud %", 0.9, "right", True),
    ]
    return Tabla(
        "asistencia-detallada", "Asistencia detallada",
        "Un registro por alumno y sesión. No incluye clases canceladas ni sesiones por revisar.",
        columnas, filas, await _describir(db, user, f),
        _indicadores(conteo["asistio"], conteo["tardanza"], conteo["falta"], conteo["falta_justificada"]),
        truncada=truncada,
    )


async def _resumen_cursos(db, user, f: Filtros) -> Tabla:
    donde, params = _where(user, f)
    sql = (
        "SELECT c.cycle, c.code, c.name, cg.group_code, t.full_name AS docente, "
        "COUNT(DISTINCT ar.student_id) AS alumnos, COUNT(DISTINCT s.id) AS sesiones, "
        + SUMA_ESTADOS + FROM_BASE + donde +
        "GROUP BY c.cycle, c.code, c.name, cg.id, cg.group_code, t.full_name "
        "ORDER BY c.cycle, c.code, cg.group_code"
    )
    registros = (await db.exec(sql_text(sql).bindparams(**params))).all()
    filas, a, t, fa, fj = [], 0, 0, 0, 0
    for r in registros:
        a, t, fa, fj = a + r.asistio, t + r.tardanza, fa + r.falta, fj + r.justificada
        pct = _porcentaje(r.asistio + r.tardanza, r.total)
        filas.append([
            Celda(ROMANOS.get(r.cycle, r.cycle)), Celda(r.code), Celda(r.name), Celda(r.group_code),
            Celda(r.docente or "Sin docente"), Celda(r.alumnos), Celda(r.sesiones),
            Celda(r.asistio), Celda(r.tardanza), Celda(r.falta), Celda(r.justificada),
            Celda(pct, "ok" if pct >= 80 else "warn" if pct >= 70 else "bad"),
        ])
    columnas = [
        Columna("ciclo", "Ciclo", 0.6, "center"), Columna("codigo", "Código", 0.9),
        Columna("curso", "Curso", 2.8), Columna("grupo", "Grupo", 0.6, "center"),
        Columna("docente", "Docente", 2.2), Columna("alumnos", "Alumnos", 0.8, "right", True),
        Columna("sesiones", "Sesiones", 0.8, "right", True), Columna("asistio", "Asistió", 0.8, "right", True),
        Columna("tardanza", "Tardanza", 0.8, "right", True), Columna("falta", "Faltas", 0.7, "right", True),
        Columna("just", "Justif.", 0.7, "right", True), Columna("pct", "% Asist.", 0.9, "right", True),
    ]
    return Tabla(
        "resumen-por-curso", "Resumen por curso y grupo",
        "Totales de asistencia por grupo. El porcentaje cuenta asistencias y tardanzas sobre todos los registros.",
        columnas, filas, await _describir(db, user, f), _indicadores(a, t, fa, fj),
    )


async def _resumen_estudiantes(db, user, f: Filtros) -> Tabla:
    donde, params = _where(user, f)
    sql = (
        "SELECT st.full_name AS alumno, st.code AS codigo, c.code AS curso_codigo, c.name AS curso, "
        "cg.group_code AS grupo, " + SUMA_ESTADOS + FROM_BASE + donde +
        "GROUP BY st.id, st.full_name, st.code, c.id, c.code, c.name, cg.id, cg.group_code "
        "ORDER BY st.full_name, c.code"
    )
    registros = (await db.exec(sql_text(sql).bindparams(**params))).all()
    alerta, limite = await _niveles(db)
    filas, a, t, fa, fj = [], 0, 0, 0, 0
    for r in registros:
        inasistencia = _porcentaje(r.falta, r.total)
        nivel, tono = _nivel(inasistencia, alerta, limite)
        if f.solo_riesgo and nivel == "Normal":
            continue
        a, t, fa, fj = a + r.asistio, t + r.tardanza, fa + r.falta, fj + r.justificada
        pct = _porcentaje(r.asistio + r.tardanza, r.total)
        filas.append([
            Celda(r.alumno), Celda(r.codigo or "—"), Celda(f"{r.curso_codigo} · {r.curso}"),
            Celda(r.grupo), Celda(r.total), Celda(r.asistio), Celda(r.tardanza), Celda(r.falta),
            Celda(r.justificada), Celda(pct), Celda(inasistencia), Celda(nivel, tono),
        ])
    columnas = [
        Columna("alumno", "Estudiante", 2.6), Columna("codigo", "Código", 1.0),
        Columna("curso", "Curso", 2.8), Columna("grupo", "Grupo", 0.6, "center"),
        Columna("sesiones", "Sesiones", 0.8, "right", True), Columna("asistio", "Asistió", 0.8, "right", True),
        Columna("tardanza", "Tardanza", 0.8, "right", True), Columna("falta", "Faltas", 0.7, "right", True),
        Columna("just", "Justif.", 0.7, "right", True), Columna("pct", "% Asist.", 0.9, "right", True),
        Columna("inasist", "% Inasist.", 0.9, "right", True), Columna("nivel", "Nivel", 0.9, "center"),
    ]
    resumen = _indicadores(a, t, fa, fj)
    return Tabla(
        "resumen-por-estudiante", "Resumen por estudiante",
        f"Nivel de riesgo: alerta desde {alerta:.0f}% de inasistencia y límite sobre {limite:.0f}%.",
        columnas, filas, await _describir(db, user, f), resumen,
    )


async def _riesgo(db, user, f: Filtros) -> Tabla:
    from app.services.dpi import sesiones_planificadas
    from app.services.settings import get_settings_row

    alerta, limite = await _niveles(db)
    sql = (
        "SELECT v.student_id, v.course_id, v.course_code, v.course_name, v.sessions_held, "
        "v.absences, v.justified_absences, v.lates, v.absence_percent, "
        "u.full_name AS student_name, u.code AS student_code "
        "FROM v_student_dpi v JOIN app_user u ON u.id = v.student_id "
        "JOIN course c ON c.id = v.course_id WHERE v.absence_percent >= :alerta"
    )
    params: dict = {"alerta": alerta}
    if f.course_id is not None:
        sql += " AND v.course_id = :curso"
        params["curso"] = f.course_id
    if f.cycle is not None:
        sql += " AND c.cycle = :ciclo"
        params["ciclo"] = f.cycle
    if f.q and f.q.strip():
        sql += " AND (u.full_name ILIKE :q OR u.code ILIKE :q)"
        params["q"] = f"%{f.q.strip()}%"
    if user.role is UserRole.DOCENTE:
        sql += (" AND v.course_id IN (SELECT cg.course_id FROM course_group cg "
                "WHERE cg.teacher_id = :docente AND cg.is_active)")
        params["docente"] = user.id
    sql += " ORDER BY v.absence_percent DESC, u.full_name LIMIT 5000"
    registros = (await db.exec(sql_text(sql).bindparams(**params))).all()
    cfg = await get_settings_row(db)
    filas, en_limite = [], 0
    for r in registros:
        pct = float(r.absence_percent)
        plan = await sesiones_planificadas(db, int(r.student_id), int(r.course_id), cfg)
        permitidas = int(plan * limite / 100) if plan is not None else None
        nivel, tono = _nivel(pct, alerta, limite)
        en_limite += nivel == "Límite"
        filas.append([
            Celda(r.student_name), Celda(r.student_code or "—"), Celda(f"{r.course_code} · {r.course_name}"),
            Celda(int(r.sessions_held)), Celda(int(r.absences)), Celda(int(r.justified_absences)),
            Celda(int(r.lates)), Celda(round(pct, 1)), Celda(nivel, tono),
            Celda(permitidas if permitidas is not None else "—"),
            Celda(max(0, permitidas - int(r.absences)) if permitidas is not None else "—"),
        ])
    columnas = [
        Columna("alumno", "Estudiante", 2.6), Columna("codigo", "Código", 1.0), Columna("curso", "Curso", 2.8),
        Columna("sesiones", "Sesiones", 0.8, "right", True), Columna("faltas", "Faltas", 0.7, "right", True),
        Columna("just", "Justif.", 0.7, "right", True), Columna("tardanzas", "Tardanzas", 0.9, "right", True),
        Columna("pct", "% Inasist.", 0.9, "right", True), Columna("nivel", "Nivel", 0.9, "center"),
        Columna("permitidas", "Permitidas", 0.9, "right", True), Columna("restantes", "Restantes", 0.9, "right", True),
    ]
    indicadores = [
        Indicador("Alumnos en riesgo", str(len(filas)), "warn" if filas else "ok"),
        Indicador("En el límite", str(en_limite), "bad" if en_limite else "ok"),
        Indicador("En alerta", str(len(filas) - en_limite), "warn"),
    ]
    filtros = [("Periodo", "Vigente"), ("Alerta", f"≥ {alerta:.0f}%"), ("Límite", f"> {limite:.0f}%")]
    if f.course_id is not None:
        curso = await db.get(Course, f.course_id)
        if curso:
            filtros.append(("Curso", f"{curso.code} · {curso.name}"))
    if f.cycle is not None:
        filtros.append(("Ciclo", ROMANOS.get(f.cycle, str(f.cycle))))
    if f.q and f.q.strip():
        filtros.append(("Alumno", f.q.strip()))
    return Tabla(
        "riesgo-de-inasistencia", "Riesgo de inasistencia",
        "Alumnos en alerta o sobre el límite de faltas, con las faltas que les quedan.",
        columnas, filas, filtros, indicadores,
    )


CONSTRUCTORES = {
    "attendance": _detalle,
    "course-summary": _resumen_cursos,
    "student-summary": _resumen_estudiantes,
    "dpi-risk": _riesgo,
}


async def construir_reporte(db, user, clave: str, filtros: Filtros) -> Tabla:
    return await CONSTRUCTORES[clave](db, user, filtros)
