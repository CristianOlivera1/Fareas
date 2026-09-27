"""Health check: monitorea la app y la conexión a PostgreSQL real (RF-35)."""
from fastapi import APIRouter
from sqlmodel import func, select

from app.core.config import get_settings
from app.core.deps import DbSession
from app.tables import AppUser

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(db: DbSession) -> dict:
    settings = get_settings()
    payload: dict = {
        "status": "ok",
        "app": settings.APP_NAME,
        "environment": settings.ENVIRONMENT,
    }
    try:
        # Un SELECT ORM trivial valida engine, driver asyncpg y mapeo de tablas.
        users = (await db.exec(select(func.count()).select_from(AppUser))).one()
        payload["database"] = "ok"
        payload["users"] = users
    except Exception:  # noqa: BLE001 - el health nunca debe lanzar 500 por la BD
        payload["database"] = "unavailable"
    return payload
