"""Tareas periódicas (APScheduler dentro del proceso).

- R3: APERTURA automática de sesiones (cada 60 s, cuando la ventana de
  apertura de un bloque empieza — aunque nadie marque).
- RF-26/R4: cierre automático de sesiones vencidas (faltas + needs_review +
  alertas DPI) cada 60 s.
- RF-35: expiración de nodos ESP32 sin latidos (>90 s → is_online=FALSE).
Usa su PROPIA sesión de BD por barrido (no comparte el request-scoped).
"""
import contextlib
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.database import SessionLocal

logger = logging.getLogger("fareas.scheduler")

_scheduler: AsyncIOScheduler | None = None


async def _barrido() -> None:
    """Una pasada del scheduler (a prueba de fallos: nunca revienta; registra
    y sigue): abre sesiones (R3), cierra vencidas (R4), expira nodos (RF-35)."""
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
        await expirar_nodos()  # RF-35: 90 s sin latidos → is_online=FALSE


def iniciar_scheduler(intervalo_segundos: int = 60) -> AsyncIOScheduler:
    """Arranca el job de apertura/cierre (idempotente)."""
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
