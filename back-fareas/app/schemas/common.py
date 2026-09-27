"""DTOs transversales compartidos por todos los módulos.

Equivale al ``Helper/ApiResponseHelper`` + ``Objects/QueryResult`` del
proyecto Laravel de referencia: una envoltura uniforme de respuesta y una
página genérica para los listados.
"""
from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class MessageResponse(BaseModel):
    """Respuesta uniforme de acciones sin cuerpo de retorno."""

    message: str


class Page(BaseModel, Generic[T]):
    """Página de un listado (metadatos + items)."""

    items: list[T]
    total: int
    page: int
    page_size: int

    @property
    def pages(self) -> int:
        return (self.total + self.page_size - 1) // self.page_size if self.page_size else 0
