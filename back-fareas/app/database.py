"""Motor y sesión asíncronos sobre PostgreSQL 17 (asyncpg + SQLModel).

Esquema de BD gestionado manualmente con scripts SQL en back-fareas/db/
(001_schema.sql, 002_seed.sql, 00N_*.sql). El código NUNCA ejecuta
create_all(): la base manda, los modelos de app/tables.py la mapean.
"""
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from app.core.config import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=not settings.is_production,
    pool_pre_ping=True,
)

# AsyncSession de SQLModel: añade .exec() sobre la sesión de SQLAlchemy.
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=SQLModelAsyncSession)


async def get_db() -> AsyncGenerator[SQLModelAsyncSession]:
    """Dependencia FastAPI: una sesión por request, cerrada siempre al final."""
    async with SessionLocal() as session:
        yield session
