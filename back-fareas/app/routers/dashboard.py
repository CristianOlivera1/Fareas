"""Dashboard — RF-13 (panel en vivo) y mapeo PLAN §5: summary, feed SSE y
estadísticas para los widgets Angular.

- ``GET /dashboard/summary``   → tarjetas (asistencias, ausencias, cámaras, DPI).
- ``GET /dashboard/live``      → SSE con los veredictos del bucle de cámaras
  (``camera_loop``). EventSource NO puede enviar cabeceras: el JWT llega por
  query ``?access_token=`` (patrón estándar para SSE autenticado).
- ``GET /dashboard/live-room/{room_id}`` → ídem, filtrado a un aula.
- ``GET /stats/hourly``        → marcas por hora de inicio de bloque (07–20).
- ``GET /stats/distribution``  → dona Asistió/Tardanza/Falta/Sin registro.

La fuente de verdad es la BD (tablas del esquema 001); los veredictos en vivo
vienen de memoria (``camera_loop._ultimo``), sin Redis ni Celery (PLAN §7).
"""
import asyncio
import json
import logging
from datetime import date, datetime

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text as sql_text
from sqlmodel import select
from sse_starlette.sse import EventSourceResponse

from app.core.deps import CurrentUser, DbSession
from app.core.security import decode_access_token
from app.database import SessionLocal
from app.services.camera_loop import todos_los_veredictos
from app.tables import AppUser, UserRole

logger = logging.getLogger("fareas.dashboard")
router = APIRouter(tags=["dashboard"])

# ---------------------------------------------------------------------------
# 1) Resumen de tarjetas — RF-13
# ---------------------------------------------------------------------------
class Summary(BaseModel):
    asistencias_hoy: int
    tardanzas_hoy: int
    ausencias_hoy: int
    total_marcas_hoy: int
    pct_ausentismo: float
    camaras_total: int
    camaras_activas: int
    streams_caidos: int
    alertas_dpi: int
    at: str


async def _contar_marcas_hoy(db) -> dict:
    """Tarjetas 1-2: marcas de HOY (sesiones abiertas y cerradas).

    Ausencias = registros 'falta' de hoy (cierres o manuales); los matriculados
    de sesiones aún ABIERTAS sin marca no cuentan: todavía pueden llegar.
    """
    sql = (
        "SELECT ar.status::text AS status, COUNT(*) "
        "FROM attendance_record ar "
        "JOIN attendance_session s ON s.id = ar.session_id "
        "WHERE s.session_date = CURRENT_DATE GROUP BY ar.status"
    )
    rows = (await db.exec(sql_text(sql))).all()
    conteo = {r[0]: r[1] for r in rows}
    asistio = conteo.get("asistio", 0)
    tardanza = conteo.get("tardanza", 0)
    falta = conteo.get("falta", 0)
    total = asistio + tardanza + falta
    return {
        "asistencias": asistio,
        "tardanzas": tardanza,
        "ausencias": falta,
        "total": total,
        "pct": round(falta * 100.0 / total, 1) if total else 0.0,
    }


async def _contar_camaras(db) -> dict:
    """Tarjeta 3: cámaras registradas y activas en el catálogo (RF-05)."""
    sql = "SELECT COUNT(*) FROM device WHERE is_active AND device_type = 'camara'"
    total = (await db.exec(sql_text(sql))).scalar_one()
    return {"total": total, "activas": total}


async def _contar_alertas_dpi(db) -> int:
    """Tarjeta 4: alumnos en/por encima del umbral DPI (RF-24, v_student_dpi)."""
    sql = (
        "SELECT COUNT(*) FROM v_student_dpi v "
        "CROSS JOIN app_settings st WHERE st.id = 1 "
        "AND v.absence_percent >= st.dpi_alert_percent"
    )
    return (await db.exec(sql_text(sql))).scalar_one()


@router.get("/dashboard/summary", response_model=Summary)
async def summary(db: DbSession, _user: CurrentUser) -> Summary:
    """Tarjetas superiores del dashboard (RF-13, PLAN §5)."""
    marcas = await _contar_marcas_hoy(db)
    camaras = await _contar_camaras(db)
    alertas = await _contar_alertas_dpi(db)
    return Summary(
        asistencias_hoy=marcas["asistencias"],
        tardanzas_hoy=marcas["tardanzas"],
        ausencias_hoy=marcas["ausencias"],
        total_marcas_hoy=marcas["total"],
        pct_ausentismo=marcas["pct"],
        camaras_total=camaras["total"],
        camaras_activas=camaras["activas"],
        streams_caidos=camaras["total"] - camaras["activas"],
        alertas_dpi=alertas,
        at=datetime.now().isoformat(timespec="seconds"),
    )


# ---------------------------------------------------------------------------
# 2) Feed en vivo — SSE (RF-13): reemplaza el setInterval del mock Angular
# ---------------------------------------------------------------------------
async def _usuario_de_token(access_token: str) -> AppUser:
    """Auth para SSE: EventSource no manda headers → token por query."""
    try:
        payload = decode_access_token(access_token)
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Token inválido o expirado") from exc
    async with SessionLocal() as db:
        user = (await db.exec(select(AppUser).where(AppUser.id == payload.user_id))).first()
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="Usuario inexistente o inactivo")
    if user.role not in (UserRole.ADMIN, UserRole.DOCENTE):
        raise HTTPException(status_code=403, detail="No tienes permisos para esta operación")
    return user


@router.get("/dashboard/live")
async def dashboard_live(
    access_token: str = Query(..., min_length=10),
    room_id: int | None = Query(None, description="Filtra por aula"),
) -> EventSourceResponse:
    await _usuario_de_token(access_token)

    async def generador():
        ultimo_enviado: dict[int, str] = {}
        try:
            while True:
                for v in todos_los_veredictos():
                    if room_id is not None and v.get("room_id") != room_id:
                        continue
                    ts = str(v.get("ts", ""))
                    if ultimo_enviado.get(v.get("room_id")) != ts:
                        ultimo_enviado[v.get("room_id")] = ts
                        yield {"event": "verdict", "data": json.dumps(v, ensure_ascii=False)}
                await asyncio.sleep(1.0)
        except asyncio.CancelledError:
            raise
        finally:
            logger.info("Cliente SSE desconectado (room_id=%s)", room_id)

    # ping=15: comentario SSE cada 15 s para no perder la conexión por proxies
    return EventSourceResponse(generador(), ping=15)


@router.get("/dashboard/live-room/{room_id}")
async def dashboard_live_room(
    room_id: int,
    access_token: str = Query(..., min_length=10),
) -> EventSourceResponse:
    """SSE de UN aula (cámara/ESP32 del aula en el panel de monitoreo)."""
    return await dashboard_live(access_token=access_token, room_id=room_id)


# ---------------------------------------------------------------------------
# 3) Estadísticas para los gráficos (PLAN §5)
# ---------------------------------------------------------------------------
HORA_INICIO, HORA_FIN = 7, 20  # franja institucional (app_settings 07:00–20:00)


@router.get("/stats/hourly")
async def stats_hourly(
    db: DbSession,
    _user: CurrentUser,
    day: date | None = Query(None, description="Día a consultar (default: hoy)"),
) -> list[dict]:
    """Marcas por hora de inicio de bloque (widget app-hourly-chart).

    La 'hora' es la del BLOQUE, no marked_at: así la curva muestra la carga
    de la franja 07–20 aunque la marca facial llegue minutos después.
    """
    dia = day or date.today()
    sql = (
        "SELECT EXTRACT(HOUR FROM sb.start_time)::int AS hora, ar.status::text AS status, COUNT(*) "
        "FROM attendance_record ar "
        "JOIN attendance_session s ON s.id = ar.session_id "
        "JOIN schedule_block sb ON sb.id = s.block_id "
        "WHERE s.session_date = :dia "
        "GROUP BY 1, 2 ORDER BY 1"
    )
    rows = (await db.exec(sql_text(sql).bindparams(dia=dia))).all()
    por_hora: dict[int, dict[str, int]] = {}
    for hora, status_, total in rows:
        h = por_hora.setdefault(int(hora), {"asistio": 0, "tardanza": 0, "falta": 0})
        h[status_] = h.get(status_, 0) + total
    serie = []
    for hora in range(HORA_INICIO, HORA_FIN + 1):
        h = por_hora.get(hora, {"asistio": 0, "tardanza": 0, "falta": 0})
        serie.append({
            "hour": f"{hora:02d}:00",
            "asistio": h["asistio"],
            "tardanza": h["tardanza"],
            "falta": h["falta"],
            "total": sum(h.values()),
        })
    return serie


@router.get("/stats/distribution")
async def stats_distribution(
    db: DbSession,
    _user: CurrentUser,
    desde: date | None = Query(None),
    hasta: date | None = Query(None),
) -> dict:
    """Dona Asistió/Tardanza/Falta/Sin registro (widget app-distribution-chart).

    ``sin_registro`` = matriculados de sesiones CERRADAS del rango sin marca
    (los 'faltados por cierre' ya son falta; esto cubre huecos históricos).
    """
    hoy = date.today()
    d1, d2 = desde or hoy, hasta or hoy
    if d1 > d2:
        raise HTTPException(status_code=422, detail="'desde' no puede ser mayor que 'hasta'")

    sql = (
        "SELECT ar.status::text AS status, COUNT(*) "
        "FROM attendance_record ar "
        "JOIN attendance_session s ON s.id = ar.session_id "
        "WHERE s.session_date BETWEEN :d1 AND :d2 GROUP BY ar.status"
    )
    rows = (await db.exec(sql_text(sql).bindparams(d1=d1, d2=d2))).all()
    out = {"asistio": 0, "tardanza": 0, "falta": 0, "sin_registro": 0}
    for status_, total in rows:
        if status_ in out:
            out[status_] = total

    sql_sin = (
        "SELECT COUNT(*) FROM enrollment e "
        "JOIN course_group cg ON cg.id = e.group_id "
        "JOIN schedule_block sb ON sb.group_id = cg.id "
        "JOIN attendance_session s ON s.block_id = sb.id "
        " AND s.status = 'cerrada' AND s.session_date BETWEEN :d1 AND :d2 "
        "LEFT JOIN attendance_record ar ON ar.session_id = s.id AND ar.student_id = e.student_id "
        "WHERE ar.id IS NULL"
    )
    out["sin_registro"] = (await db.exec(sql_text(sql_sin).bindparams(d1=d1, d2=d2))).scalar_one()
    return out
