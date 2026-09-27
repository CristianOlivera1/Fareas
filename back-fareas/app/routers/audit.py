"""Bitácora de acciones sensibles - RF-32 (solo lectura, admin).

La escritura se hace desde ``app/services/audit.py`` dentro de la transacción
de cada operación; aquí solo se consulta con filtros y paginación.
"""
from datetime import datetime

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlmodel import func, select

from app.core.deps import DbSession, RequireRole
from app.core.pagination import PageParamsDep
from app.schemas.common import Page
from app.tables import AppUser, AuditLog, UserRole

router = APIRouter(tags=["audit"])


class AuditEntryOut(BaseModel):
    id: int
    action: str
    entity: str
    entity_id: int | None
    actor_id: int | None
    actor_name: str | None
    old_value: dict | list | None
    new_value: dict | list | None
    ip_address: str | None
    created_at: str | None


@router.get("/audit-log", response_model=Page[AuditEntryOut])
async def list_audit_log(
    db: DbSession,
    _admin: RequireRole(UserRole.ADMIN),
    page: PageParamsDep,
    action: str | None = Query(None, max_length=40),
    entity: str | None = Query(None, max_length=40),
    entity_id: int | None = None,
    actor_id: int | None = None,
    since: datetime | None = Query(None, description="Filtro ISO p. ej. 2026-09-01T00:00:00"),  # noqa: B008
) -> Page[AuditEntryOut]:
    stmt = select(AuditLog, AppUser).outerjoin(AppUser, AppUser.id == AuditLog.actor_id)
    count_stmt = select(func.count()).select_from(AuditLog)
    if action:
        stmt = stmt.where(AuditLog.action == action)
        count_stmt = count_stmt.where(AuditLog.action == action)
    if entity:
        stmt = stmt.where(AuditLog.entity == entity)
        count_stmt = count_stmt.where(AuditLog.entity == entity)
    if entity_id is not None:
        stmt = stmt.where(AuditLog.entity_id == entity_id)
        count_stmt = count_stmt.where(AuditLog.entity_id == entity_id)
    if actor_id is not None:
        stmt = stmt.where(AuditLog.actor_id == actor_id)
        count_stmt = count_stmt.where(AuditLog.actor_id == actor_id)
    if since is not None:
        stmt = stmt.where(AuditLog.created_at >= since)  # type: ignore[arg-type]
        count_stmt = count_stmt.where(AuditLog.created_at >= since)  # type: ignore[arg-type]

    total = (await db.exec(count_stmt)).one()
    rows = (
        await db.exec(stmt.order_by(AuditLog.created_at.desc()).offset(page.offset).limit(page.limit))
    ).all()
    items = [
        AuditEntryOut(
            id=log.id,  # type: ignore[arg-type]
            action=log.action,
            entity=log.entity,
            entity_id=log.entity_id,
            actor_id=log.actor_id,
            actor_name=actor.full_name if actor else None,
            old_value=log.old_value,
            new_value=log.new_value,
            ip_address=log.ip_address,
            created_at=log.created_at.isoformat(timespec="seconds") if log.created_at else None,
        )
        for log, actor in rows
    ]
    return Page(items=items, total=total, page=page.page, page_size=page.page_size)
