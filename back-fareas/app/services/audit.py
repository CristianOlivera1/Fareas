import json
from typing import Any

from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from app.tables import AppUser, AuditLog


def _json(value: Any) -> Any:
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
    db.add(
        AuditLog(
            actor_id=actor.id if actor is not None else None,
            action=action,
            entity=entity,
            entity_id=entity_id,
            old_value=_json(old_value),
            new_value=_json(new_value),
            ip_address=ip_address,
        )
    )
