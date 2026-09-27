"""Escritura en la bitácora de acciones sensibles (RF-32).

Equivalente al ``Observers`` de Laravel: cada acción que el reglamento exige
auditar llama aquí ANTES de confirmar la transacción, de modo que el registro
vive y muere con la misma transacción (si algo falla, no queda audit_log
huérfano). La lectura admin vive en ``routers/audit.py``.
"""
import json
from typing import Any

from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from app.tables import AppUser, AuditLog


def _json(value: Any) -> Any:
    """Normaliza el valor para la columna JSONB: los dicts/lists pasan tal cual
    (SQLAlchemy los serializa); los tipos no serializables (datetime, Decimal)
    se convierten con default=str."""
    if value is None:
        return None
    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        return json.loads(json.dumps(value, default=str))


async def audit(
    db: SQLModelAsyncSession,
    actor: AppUser | None,
    action: str,
    entity: str,
    entity_id: int | None = None,
    old_value: Any = None,
    new_value: Any = None,
    ip_address: str | None = None,
) -> None:
    """Registra una acción en audit_log dentro de la sesión/transacción actual.

    ``actor=None`` = el sistema (scheduler, procesos automáticos).
    """
    db.add(
        AuditLog(
            actor_id=actor.id if actor is not None else None,  # type: ignore[arg-type]
            action=action,
            entity=entity,
            entity_id=entity_id,
            old_value=_json(old_value),
            new_value=_json(new_value),
            ip_address=ip_address,
        )
    )
