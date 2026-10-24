from datetime import date
from itertools import count
from types import SimpleNamespace

import pytest
from sqlmodel import delete, select

from app.routers import calendar_admin
from app.services import justifications as justifications_service
from app.services.storage import LocalStorage
from app.tables import AppUser, Justification, UserRole

API = "/api/v1"
STUDENT_EMAIL = "temp.justdoc@unamba.edu.pe"
_student_codes = count(700000)

PDF = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n%%EOF\n"
JPEG = b"\xff\xd8\xff\xe0" + b"0" * 64


@pytest.fixture
async def local_storage(tmp_path, monkeypatch):
    storage = LocalStorage(str(tmp_path))
    monkeypatch.setattr(calendar_admin, "get_storage", lambda: storage)
    monkeypatch.setattr(justifications_service, "get_storage", lambda: storage)
    return storage


@pytest.fixture
async def justification(db_session, local_storage):
    await db_session.exec(delete(Justification).where(Justification.reason == "Reposo médico documentado"))
    student = (
        await db_session.exec(select(AppUser).where(AppUser.email == STUDENT_EMAIL))
    ).first()
    if student is None:
        student = AppUser(
            role=UserRole.ESTUDIANTE,
            email=STUDENT_EMAIL,
            code=str(next(_student_codes)),
            full_name="Estudiante Temporal Adjuntos",
            password_hash="x" * 20,
            must_change_password=False,
        )
        db_session.add(student)
        await db_session.commit()
    admin = (
        await db_session.exec(select(AppUser).where(AppUser.email == "admin@unamba.edu.pe"))
    ).first()
    just = Justification(
        student_id=student.id,
        course_id=None,
        start_date=date.today(),
        end_date=date.today(),
        reason="Reposo médico documentado",
        created_by=admin.id,
    )
    db_session.add(just)
    await db_session.commit()
    await db_session.refresh(just)
    yield just
    await db_session.exec(delete(Justification).where(Justification.id == just.id))
    await db_session.exec(delete(AppUser).where(AppUser.id == student.id))
    await db_session.commit()


async def test_subida_listado_y_reemplazo(client, admin_headers, db_session, justification, tmp_path):
    r = await client.post(
        f"{API}/justifications/{justification.id}/document",
        headers=admin_headers,
        files={"file": ("constancia.pdf", PDF, "application/pdf")},
    )
    assert r.status_code == 200, r.text
    assert r.json()["document_url"]

    await db_session.refresh(justification)
    first_key = justification.document_key
    assert first_key is not None
    assert first_key.endswith(".pdf")
    assert len(list(tmp_path.glob("*.pdf"))) == 1

    r = await client.get(f"{API}/justifications", headers=admin_headers)
    assert r.status_code == 200
    item = next(j for j in r.json() if j["id"] == justification.id)
    assert item["document_url"] == first_key

    r = await client.post(
        f"{API}/justifications/{justification.id}/document",
        headers=admin_headers,
        files={"file": ("foto.jpg", JPEG, "image/jpeg")},
    )
    assert r.status_code == 200, r.text
    await db_session.refresh(justification)
    assert justification.document_key != first_key
    assert justification.document_key.endswith(".jpg")
    assert not list(tmp_path.glob("*.pdf"))
    assert len(list(tmp_path.glob("*.jpg"))) == 1


async def test_rechaza_archivo_que_no_es_documento(
    client, admin_headers, db_session, justification
):
    r = await client.post(
        f"{API}/justifications/{justification.id}/document",
        headers=admin_headers,
        files={"file": ("nota.pdf", b"esto no es un pdf", "application/pdf")},
    )
    assert r.status_code == 415
    await db_session.refresh(justification)
    assert justification.document_key is None


async def test_rechaza_archivo_demasiado_grande(
    client, admin_headers, justification, monkeypatch
):
    monkeypatch.setattr(
        calendar_admin, "get_settings", lambda: SimpleNamespace(R2_MAX_UPLOAD_MB=1)
    )
    oversized = PDF + b"0" * (1024 * 1024)
    r = await client.post(
        f"{API}/justifications/{justification.id}/document",
        headers=admin_headers,
        files={"file": ("grande.pdf", oversized, "application/pdf")},
    )
    assert r.status_code == 413


async def test_borrar_documento_y_justificacion_elimina_el_objeto(
    client, admin_headers, db_session, justification, tmp_path
):
    r = await client.post(
        f"{API}/justifications/{justification.id}/document",
        headers=admin_headers,
        files={"file": ("constancia.pdf", PDF, "application/pdf")},
    )
    assert r.status_code == 200
    await db_session.refresh(justification)
    assert justification.document_key is not None
    assert len(list(tmp_path.iterdir())) == 1

    r = await client.delete(
        f"{API}/justifications/{justification.id}/document", headers=admin_headers
    )
    assert r.status_code == 200
    await db_session.refresh(justification)
    assert justification.document_key is None
    assert list(tmp_path.iterdir()) == []

    r = await client.delete(
        f"{API}/justifications/{justification.id}/document", headers=admin_headers
    )
    assert r.status_code == 404

    r = await client.post(
        f"{API}/justifications/{justification.id}/document",
        headers=admin_headers,
        files={"file": ("constancia.pdf", PDF, "application/pdf")},
    )
    assert r.status_code == 200

    r = await client.delete(
        f"{API}/justifications/{justification.id}", headers=admin_headers
    )
    assert r.status_code == 200
    assert list(tmp_path.iterdir()) == []


async def test_docente_ajeno_no_puede_adjuntar(
    client, docente_headers, justification
):
    r = await client.post(
        f"{API}/justifications/{justification.id}/document",
        headers=docente_headers,
        files={"file": ("constancia.pdf", PDF, "application/pdf")},
    )
    assert r.status_code == 403
