"""Dependencia de paginación para los listados del catálogo.

Rescata la idea del ``Helper/PaginationHelper`` de Laravel, pero en la forma
nativa de FastAPI: una dependencia ``Annotated`` que cualquier endpoint recibe
como parámetro (SIEMPRE via ``Depends``; un valor por defecto directo NO se
resuelve). El tope evita que un cliente pida 100 000 filas.
"""
from dataclasses import dataclass
from math import ceil
from typing import Annotated

from fastapi import Depends, Query


@dataclass(frozen=True)
class PageParams:
    page: int
    page_size: int

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size

    @property
    def limit(self) -> int:
        return self.page_size

    def pages_for(self, total: int) -> int:
        return ceil(total / self.page_size) if self.page_size else 0


def page_params(
    page: int = Query(1, ge=1, description="Número de página (1-based)"),
    page_size: int = Query(20, ge=1, le=100, description="Filas por página (máx. 100)"),
) -> PageParams:
    return PageParams(page=page, page_size=page_size)


# Forma de uso en endpoints:  page: PageParamsDep
# (Depends es OBLIGATORIO: un valor por defecto tipo page=page_params() no se
# resuelve y llegaría el objeto Query crudo a la función.)
PageParamsDep = Annotated[PageParams, Depends(page_params)]
