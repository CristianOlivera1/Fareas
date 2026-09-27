"""Excepciones de dominio de los servicios (idea rescatada de Laravel:
``InsufficientCreditsException`` etc.), mapeadas a HTTP en un solo lugar.

Los routers/servicios lanzan estas excepciones; los handlers de
``app/main.py`` las convierten en respuestas HTTP coherentes. Así el código
de negocio nunca arma HTTPException a mano y los mensajes quedan uniformes.
"""


class DomainError(Exception):
    """Base: un servicio detecta una regla de negocio rota."""


class ConflictError(DomainError):
    """Recurso duplicado o choque de horarios → 409."""


class NotFoundError(DomainError):
    """El recurso referenciado no existe → 404."""
