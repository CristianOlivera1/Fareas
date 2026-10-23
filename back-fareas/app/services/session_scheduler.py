import contextlib
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.database import SessionLocal

logger = logging.getLogger("fareas.scheduler")

_scheduler: AsyncIOScheduler | None = None


async def _barrido() -> None:
    from app.routers.ws_devices import expirar_nodos
    from app.services.attendance_engine import (
        abrir_sesiones_del_dia,
        cerrar_sesiones_pendientes,
    )

    try:
        async with SessionLocal() as db:
            abiertas = await abrir_sesiones_del_dia(db)
            if abiertas:
                logger.info("[R3] %s sesiones abiertas automáticamente", abiertas)
            resumenes = await cerrar_sesiones_pendientes(db)
        for r in resumenes:
            logger.info(
                "[RF-26] Sesión %s: %s (faltas=%s, alertas=%s)",
                r.get("session_id"), r.get("status"), r.get("faltas"), r.get("alertas"),
            )
    except Exception:
        logger.exception("El barrido del scheduler de asistencia falló")

    with contextlib.suppress(Exception):
        await expirar_nodos()

def iniciar_scheduler(intervalo_segundos: int = 60) -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is not None:
        return _scheduler
    _scheduler = AsyncIOScheduler()
    _scheduler.add_job(
        _barrido,
        "interval",
        seconds=intervalo_segundos,
        id="apertura_cierre_sesiones",
        max_instances=1,
        coalesce=True,
    )
    _scheduler.start()
    logger.info("Scheduler de asistencia iniciado (cada %s s)", intervalo_segundos)
    return _scheduler

def detener_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("Scheduler de asistencia detenido")
