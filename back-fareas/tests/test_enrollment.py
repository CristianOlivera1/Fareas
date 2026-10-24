import base64

import numpy as np
import pytest
from sqlmodel import delete, select

from app.tables import AppUser, FaceEmbedding

API = "/api/v1"

STUDENT_TMP_EMAIL = "temp.rostros@unamba.edu.pe"


async def _purge(db_session) -> None:
    user = (
        await db_session.exec(select(AppUser).where(AppUser.email == STUDENT_TMP_EMAIL))
    ).first()
    if user is not None:
        await db_session.exec(delete(FaceEmbedding).where(FaceEmbedding.student_id == user.id))
        await db_session.delete(user)
        await db_session.commit()

@pytest.fixture
async def estudiante_temp(client, admin_headers, db_session):
    await _purge(db_session)
    r = await client.post(
        f"{API}/students",
        headers=admin_headers,
        json={
            "full_name": "Estudiante Rostros Temp",
            "email": STUDENT_TMP_EMAIL,
            "dni": "71999888",
            "code": "997766",
            "semester": 7,
        },
    )
    assert r.status_code == 201, r.text
    student = r.json()
    yield student
    await _purge(db_session)

def _jpeg_b64(rng: np.ndarray) -> str:
    import cv2

    ok, buf = cv2.imencode(".jpg", rng)
    assert ok
    return base64.b64encode(buf.tobytes()).decode()

async def test_enrolamiento_requiere_admin_y_valida_fotos(client, docente_headers):
    r = await client.post(f"{API}/students/1/faces", headers=docente_headers,
                          json={"photos": ["a", "b", "c"]})
    assert r.status_code == 403
    r = await client.post(f"{API}/students/1/faces", json={"photos": ["a", "b", "c"]})
    assert r.status_code == 401

async def test_enrolamiento_rechaza_lotes_invalidos(client, admin_headers, estudiante_temp):
    sid = estudiante_temp["id"]
    r = await client.post(f"{API}/students/{sid}/faces", headers=admin_headers,
                          json={"photos": ["###", "###", "###"]})
    assert r.status_code == 422
    assert "consentimiento" in r.json()["detail"].lower()
    r = await client.post(f"{API}/students/{sid}/faces", headers=admin_headers,
                          json={"consent": True, "photos": [_jpeg_b64(np.zeros((100, 100, 3), np.uint8))]})
    assert r.status_code == 422
    r = await client.post(f"{API}/students/{sid}/faces", headers=admin_headers,
                          json={"consent": True, "photos": ["###", "###", "###"]})
    assert r.status_code == 422
    assert "base64" in r.json()["detail"]
    gris = np.full((160, 160, 3), 90, dtype=np.uint8)
    r = await client.post(f"{API}/students/{sid}/faces", headers=admin_headers,
                          json={"consent": True, "photos": [_jpeg_b64(gris)] * 3})
    assert r.status_code == 422
    assert "rostro" in r.json()["detail"].lower()

async def test_enrolamiento_estado_y_auditoria(client, admin_headers, docente_headers, db_session, estudiante_temp):
    sid = estudiante_temp["id"]
    r = await client.get(f"{API}/students/{sid}/faces", headers=admin_headers)
    assert r.status_code == 200
    data = r.json()
    assert data["student_id"] == sid and data["enrolled"] is False
    r = await client.get(f"{API}/students/{sid}/faces", headers=docente_headers)
    assert r.status_code == 403
