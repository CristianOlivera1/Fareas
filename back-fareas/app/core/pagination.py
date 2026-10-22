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

PageParamsDep = Annotated[PageParams, Depends(page_params)]
