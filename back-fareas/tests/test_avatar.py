import io

import pytest
from PIL import Image
from sqlmodel import delete, select

from app.core.security import create_access_token
from app.services import avatars
from app.services.storage import LocalStorage
from app.tables import AppUser, AuditLog, UserRole

API = "/api/v1"
EMAIL = "temp.avatar@unamba.edu.pe"


def _image(fmt: str, size: tuple[int, int] = (600, 400)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, (30, 90, 200)).save(buffer, format=fmt)
    return buffer.getvalue()


@pytest.fixture
async def storage(tmp_path, monkeypatch):
    local = LocalStorage(str(tmp_path))
    monkeypatch.setattr(avatars, "get_storage", lambda: local)
    return local


@pytest.fixture
async def student(db_session, storage):
    await db_session.exec(delete(AuditLog).where(AuditLog.action.like("avatar_%")))
    user = (await db_session.exec(select(AppUser).where(AppUser.email == EMAIL))).first()
    if user is None:
        user = AppUser(
            role=UserRole.ESTUDIANTE,
            email=EMAIL,
            code="993001",
            full_name="Estudiante Avatar",
            password_hash="x" * 20,
            must_change_password=False,
        )
        db_session.add(user)
    user.avatar_key = None
    await db_session.commit()
    await db_session.refresh(user)
    yield user
    await db_session.exec(delete(AuditLog).where(AuditLog.actor_id == user.id))
    await db_session.delete(user)
    await db_session.commit()


def _headers(user: AppUser) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id, 'estudiante')}"}


async def test_upload_normalizes_to_a_square_jpeg(client, student, storage, tmp_path):
    r = await client.put(
        f"{API}/auth/me/avatar",
        headers=_headers(student),
        files={"file": ("foto.png", _image("PNG"), "image/png")},
    )
    assert r.status_code == 200, r.text
    assert r.json()["avatar_url"]

    stored = next(tmp_path.iterdir())
    with Image.open(stored) as image:
        assert image.format == "JPEG"
        assert image.size == (avatars.AVATAR_SIDE, avatars.AVATAR_SIDE)


async def test_me_returns_the_avatar_url(client, student, storage):
    await client.put(
        f"{API}/auth/me/avatar",
        headers=_headers(student),
        files={"file": ("foto.jpg", _image("JPEG"), "image/jpeg")},
    )
    r = await client.get(f"{API}/auth/me", headers=_headers(student))
    assert r.status_code == 200
    assert r.json()["avatar_url"]


async def test_replacing_deletes_the_previous_file(client, student, storage, tmp_path):
    for _ in range(2):
        await client.put(
            f"{API}/auth/me/avatar",
            headers=_headers(student),
            files={"file": ("foto.jpg", _image("JPEG"), "image/jpeg")},
        )
    assert len(list(tmp_path.iterdir())) == 1


async def test_remove_clears_the_avatar(client, student, storage, tmp_path):
    await client.put(
        f"{API}/auth/me/avatar",
        headers=_headers(student),
        files={"file": ("foto.jpg", _image("JPEG"), "image/jpeg")},
    )
    r = await client.delete(f"{API}/auth/me/avatar", headers=_headers(student))
    assert r.status_code == 204
    assert list(tmp_path.iterdir()) == []
    me = await client.get(f"{API}/auth/me", headers=_headers(student))
    assert me.json()["avatar_url"] is None


async def test_rejects_files_that_are_not_images(client, student, storage):
    r = await client.put(
        f"{API}/auth/me/avatar",
        headers=_headers(student),
        files={"file": ("doc.pdf", b"%PDF-1.4 not an image", "application/pdf")},
    )
    assert r.status_code == 415


async def test_rejects_oversized_uploads(client, student, storage, monkeypatch):
    monkeypatch.setattr(avatars, "max_upload_bytes", lambda: 1024)
    monkeypatch.setattr("app.routers.profile.max_upload_bytes", lambda: 1024)
    r = await client.put(
        f"{API}/auth/me/avatar",
        headers=_headers(student),
        files={"file": ("foto.png", _image("PNG", (800, 800)), "image/png")},
    )
    assert r.status_code == 413


async def test_requires_authentication(client):
    r = await client.put(
        f"{API}/auth/me/avatar", files={"file": ("foto.png", _image("PNG"), "image/png")}
    )
    assert r.status_code == 401
