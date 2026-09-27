"""Fixtures de pytest para la API.

Patrón IMPORTANTE (lección del Bloque 3): TODO en un solo event loop.
Mezclar AsyncClient con TestClient (o sesiones directas en otro loop)
corrompe el pool de asyncpg ('Event loop is closed'). Aquí la app y las
consultas de preparación/limpieza corren en el mismo loop de cada test.
"""
from collections.abc import AsyncGenerator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import delete, select
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from app.core.config import get_settings
from app.core.security import hash_password
from app.main import create_app
from app.tables import AppUser, AuditLog, UserRole

TEMP_EMAIL = "temp.test.auth@unamba.edu.pe"
TEMP_STUDENT_EMAIL = "temp.student@unamba.edu.pe"
TEMP_STUDENT_CODE = "999999"
DOCENTE_TEMP_EMAIL = "temp.docente.login@unamba.edu.pe"


@pytest.fixture(autouse=True)
async def _dispose_engine_after_each_test():
    """pytest-asyncio crea un loop POR TEST: el pool del engine guarda
    conexiones atadas al loop del test anterior. Dispuesta al terminar cada
    test (mismo loop en el que se usaron) para que el siguiente arranque limpio."""
    yield
    from app.database import engine

    await engine.dispose()


@pytest.fixture
def app_instance() -> FastAPI:
    return create_app()


@pytest.fixture
async def client(app_instance: FastAPI) -> AsyncGenerator[AsyncClient]:
    transport = ASGITransport(app=app_instance)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def db_session() -> AsyncGenerator[SQLModelAsyncSession]:
    """Sesión independiente (mismo engine/loop del test) para preparar datos."""
    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL)
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=SQLModelAsyncSession)
    async with maker() as session:
        yield session
    await engine.dispose()


async def _cleanup(db: SQLModelAsyncSession) -> None:
    await db.exec(delete(AppUser).where(AppUser.email == TEMP_EMAIL))  # type: ignore[arg-type]
    await db.commit()


@pytest.fixture
async def temp_user(db_session: SQLModelAsyncSession) -> AsyncGenerator[AppUser]:
    """Usuario admin temporal con clave temporal (must_change_password=True)."""
    await _cleanup(db_session)  # por si un test anterior falló
    user = AppUser(
        role=UserRole.ADMIN,
        email=TEMP_EMAIL,
        full_name="Usuario Temporal de Pruebas",
        password_hash=hash_password("ClaveTemporal1"),
        must_change_password=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    yield user
    await _cleanup(db_session)


async def _cleanup_student(db: SQLModelAsyncSession) -> None:
    await db.exec(delete(AppUser).where(AppUser.email == TEMP_STUDENT_EMAIL))  # type: ignore[arg-type]
    await db.commit()


@pytest.fixture
async def temp_student(db_session: SQLModelAsyncSession) -> AsyncGenerator[AppUser]:
    """Estudiante temporal (código único 999999, no choca con el seed)."""
    await _cleanup_student(db_session)  # por si un test anterior falló
    user = AppUser(
        role=UserRole.ESTUDIANTE,
        email=TEMP_STUDENT_EMAIL,
        code=TEMP_STUDENT_CODE,
        full_name="Estudiante Temporal de Pruebas",
        password_hash=hash_password("ClaveTemporal1"),
        must_change_password=True,
        semester=9,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    yield user
    await _cleanup_student(db_session)


@pytest.fixture
async def docente_headers(
    client: AsyncClient, admin_headers: dict, db_session: SQLModelAsyncSession
) -> AsyncGenerator[dict[str, str]]:
    """Docente de PRUEBA con clave conocida (independiente del seed: la BD
    demo puede ser editada por el usuario mientras se desarrolla).
    Se crea vía API, se le fija la clave en BD y se elimina al terminar."""
    async def _purge_docente() -> None:
        old = (await db_session.exec(select(AppUser).where(AppUser.email == DOCENTE_TEMP_EMAIL))).first()
        if old is not None:
            await db_session.exec(delete(AuditLog).where(AuditLog.actor_id == old.id))  # type: ignore[attr-defined,arg-type]
            await db_session.delete(old)
            await db_session.commit()

    await _purge_docente()  # residuo de una corrida anterior
    r = await client.post(
        "/api/v1/teachers",
        headers=admin_headers,
        json={"full_name": "Docente de Pruebas", "email": DOCENTE_TEMP_EMAIL, "dni": "71333555"},
    )
    assert r.status_code == 201, r.text
    user = (await db_session.exec(select(AppUser).where(AppUser.email == DOCENTE_TEMP_EMAIL))).first()
    assert user is not None
    user.password_hash = hash_password("ClaveTemporal1")
    user.must_change_password = False
    db_session.add(user)
    await db_session.commit()
    r = await client.post("/api/v1/auth/login", json={"email": DOCENTE_TEMP_EMAIL, "password": "ClaveTemporal1"})
    assert r.status_code == 200, r.text
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
    yield headers
    await _purge_docente()


@pytest.fixture
async def admin_login(client: AsyncClient) -> dict:
    """Login con el admin del seed (auth RF-11 ya verificada en test_auth)."""
    r = await client.post("/api/v1/auth/login", json={"email": "admin@unamba.edu.pe", "password": "12345678"})
    assert r.status_code == 200, r.text
    data = r.json()
    return {"headers": {"Authorization": f"Bearer {data['access_token']}"}, "user": data["user"]}


@pytest.fixture
async def admin_headers(admin_login: dict) -> dict[str, str]:
    return admin_login["headers"]
