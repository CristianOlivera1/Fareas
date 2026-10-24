from typing import Annotated

from fastapi import APIRouter, File, HTTPException, Request, UploadFile, status

from app.core.deps import CurrentUser, DbSession
from app.routers.catalog import _client_ip
from app.services.audit import audit
from app.services.avatars import (
    InvalidAvatarError,
    avatar_url,
    delete_avatar,
    max_upload_bytes,
    store_avatar,
)

router = APIRouter(prefix="/auth/me", tags=["profile"])


async def _read_limited(file: UploadFile) -> bytes:
    limit = max_upload_bytes()
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"La foto no puede superar {limit // (1024 * 1024)} MB",
        )
    if not data:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="El archivo está vacío")
    return data


@router.put("/avatar")
async def upload_avatar(
    request: Request,
    db: DbSession,
    user: CurrentUser,
    file: Annotated[UploadFile, File()],
) -> dict:
    data = await _read_limited(file)
    try:
        key = await store_avatar(user.id, data)
    except InvalidAvatarError as exc:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No se pudo guardar la foto; intenta de nuevo en unos minutos",
        ) from exc

    previous = user.avatar_key
    user.avatar_key = key
    db.add(user)
    await audit(
        db, user, action="avatar_actualizado", entity="app_user", entity_id=user.id,
        ip_address=_client_ip(request),
    )
    await db.commit()

    if previous and previous != key:
        await delete_avatar(previous)
    return {"avatar_url": await avatar_url(key)}


@router.delete("/avatar", status_code=status.HTTP_204_NO_CONTENT)
async def remove_avatar(request: Request, db: DbSession, user: CurrentUser) -> None:
    key = user.avatar_key
    if not key:
        return
    user.avatar_key = None
    db.add(user)
    await audit(
        db, user, action="avatar_eliminado", entity="app_user", entity_id=user.id,
        ip_address=_client_ip(request),
    )
    await db.commit()
    await delete_avatar(key)
