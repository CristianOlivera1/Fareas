"""Dependencias compartidas de la API - estilo Annotated (skill oficial FastAPI).

- DbSession: sesión async de BD.
- CurrentUser: usuario autenticado por Bearer JWT (RF-11).
- RequireRole: guard de roles a nivel router/endpoint (RF-01).
"""
from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from app.core.security import decode_access_token
from app.database import get_db
from app.tables import AppUser, UserRole

DbSession = Annotated[SQLModelAsyncSession, Depends(get_db)]

_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    db: DbSession,
) -> AppUser:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Falta el token de acceso (Authorization: Bearer <token>)",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = decode_access_token(credentials.credentials)
    except Exception as exc:  # expirada o inválida
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido o expirado. Inicia sesión nuevamente.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    user = (await db.exec(select(AppUser).where(AppUser.id == payload.user_id))).first()
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuario inexistente o inactivo")
    request.state.user = user
    return user


CurrentUser = Annotated[AppUser, Depends(get_current_user)]


def require_role(*allowed: UserRole) -> Callable[[AppUser], Awaitable[AppUser]]:
    """RF-01: guard de roles. Uso:
        router = APIRouter(dependencies=[Depends(require_role(UserRole.ADMIN))])
    o por endpoint con:  user: RequireRole(UserRole.ADMIN)
    """

    async def guard(user: CurrentUser) -> AppUser:
        if user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tienes permisos para esta operación",
            )
        return user

    return guard


def RequireRole(*allowed: UserRole) -> type:  # noqa: N802 - PascalCase intencional (anotación)
    """Anotación de endpoint:  user: RequireRole(UserRole.ADMIN)."""
    return Annotated[AppUser, Depends(require_role(*allowed))]  # type: ignore[return-value]
