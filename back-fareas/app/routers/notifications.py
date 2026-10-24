from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, update
from sqlmodel import select

from app.core.deps import CurrentUser, DbSession
from app.tables import Notification

router = APIRouter(prefix="/notifications", tags=["notifications"])


class NotificationOut(BaseModel):
    id: int
    kind: str
    title: str
    message: str
    link: str | None
    severity: str
    read: bool
    created_at: datetime


class NotificationListOut(BaseModel):
    items: list[NotificationOut]
    unread: int


class UnreadOut(BaseModel):
    count: int


def _out(n: Notification) -> NotificationOut:
    return NotificationOut(
        id=n.id,
        kind=n.kind,
        title=n.title,
        message=n.message,
        link=n.link,
        severity=n.severity,
        read=n.read_at is not None,
        created_at=n.created_at,
    )


async def _unread(db, user_id: int) -> int:
    return int(
        (
            await db.exec(
                select(func.count())
                .select_from(Notification)
                .where(
                    Notification.user_id == user_id,
                    Notification.read_at.is_(None),
                )
            )
        ).one()
    )


@router.get("/unread-count", response_model=UnreadOut)
async def unread_count(db: DbSession, user: CurrentUser) -> UnreadOut:
    return UnreadOut(count=await _unread(db, user.id))


@router.get("", response_model=NotificationListOut)
async def list_notifications(
    db: DbSession,
    user: CurrentUser,
    limit: int = Query(30, ge=1, le=100),
    before_id: int | None = Query(None, gt=0),
    unread_only: bool = Query(False),
) -> NotificationListOut:
    stmt = (
        select(Notification)
        .where(Notification.user_id == user.id)
        .order_by(Notification.created_at.desc(), Notification.id.desc())
        .limit(limit)
    )
    if before_id is not None:
        stmt = stmt.where(Notification.id < before_id)
    if unread_only:
        stmt = stmt.where(Notification.read_at.is_(None))
    items = (await db.exec(stmt)).all()
    return NotificationListOut(
        items=[_out(n) for n in items],
        unread=await _unread(db, user.id),
    )


@router.post("/{notification_id}/read", response_model=UnreadOut)
async def mark_read(notification_id: int, db: DbSession, user: CurrentUser) -> UnreadOut:
    notificacion = (
        await db.exec(
            select(Notification).where(
                Notification.id == notification_id,
                Notification.user_id == user.id,
            )
        )
    ).first()
    if notificacion is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notificación no encontrada",
        )
    if notificacion.read_at is None:
        notificacion.read_at = datetime.now(UTC)
        db.add(notificacion)
        await db.commit()
    return UnreadOut(count=await _unread(db, user.id))


@router.post("/read-all", response_model=UnreadOut)
async def mark_all_read(db: DbSession, user: CurrentUser) -> UnreadOut:
    await db.exec(
        update(Notification)
        .where(
            Notification.user_id == user.id,
            Notification.read_at.is_(None),
        )
        .values(read_at=datetime.now(UTC))
    )
    await db.commit()
    return UnreadOut(count=0)
