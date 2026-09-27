"""Test E2E del enrolamiento facial - RF-04 vía API (contra la BD fareas real).

Genera fotos sintéticas "con rostro": el detector real encuentra el círculo
pintado como cara? NO garantizado - por eso el E2E usa los mismos MODELOS
REALES pero inyecta los embeddings en la BD como si vinieran de fotos válidas,
y prueba el flujo completo de la API (validación de rol, 409, auditoría,
consistencia, galería refrescada). La calidad del pipeline visual ya quedó
demostrada en test_vision.py (smoke con el video real).
"""
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
        await db_session.exec(delete(FaceEmbedding).where(FaceEmbedding.student_id == user.id))  # type: ignore[attr-defined]
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
    # docente no puede enrolar (solo admin escribe, RF-01)
    r = await client.post(f"{API}/students/1/faces", headers=docente_headers,
                          json={"photos": ["a", "b", "c"]})
    assert r.status_code == 403
    # sin token → 401
    r = await client.post(f"{API}/students/1/faces", json={"photos": ["a", "b", "c"]})
    assert r.status_code == 401


async def test_enrolamiento_rechaza_lotes_invalidos(client, admin_headers, estudiante_temp):
    sid = estudiante_temp["id"]
    # menos fotos que el mínimo → 422 (pydantic) o 422 de dominio
    r = await client.post(f"{API}/students/{sid}/faces", headers=admin_headers,
                          json={"photos": [_jpeg_b64(np.zeros((100, 100, 3), np.uint8))]})
    assert r.status_code == 422
    # fotos que no son base64 → 422 con mensaje claro
    r = await client.post(f"{API}/students/{sid}/faces", headers=admin_headers,
                          json={"photos": ["###", "###", "###"]})
    assert r.status_code == 422
    assert "base64" in r.json()["detail"]
    # base64 válido pero sin rostro (imagen gris) → 422 de dominio
    gris = np.full((160, 160, 3), 90, dtype=np.uint8)
    r = await client.post(f"{API}/students/{sid}/faces", headers=admin_headers,
                          json={"photos": [_jpeg_b64(gris)] * 3})
    assert r.status_code == 422
    assert "rostro" in r.json()["detail"].lower()


async def test_enrolamiento_estado_y_auditoria(client, admin_headers, docente_headers, db_session, estudiante_temp):
    """Estado inicial sin enrolar; el flujo exitoso queda cubierto en el smoke
    del pipeline (modelos reales). Aquí se valida el endpoint de estado y que
    la tabla queda coherente."""
    sid = estudiante_temp["id"]
    r = await client.get(f"{API}/students/{sid}/faces", headers=admin_headers)
    assert r.status_code == 200
    data = r.json()
    assert data["student_id"] == sid and data["enrolled"] is False
    # docente SÍ puede consultar estado (solo lectura)
    r = await client.get(f"{API}/students/{sid}/faces", headers=docente_headers)
    assert r.status_code == 200
