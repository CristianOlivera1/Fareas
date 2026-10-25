import base64
from types import SimpleNamespace

import cv2
import numpy as np
import pytest
from sqlmodel import delete, select

from app.services import faces
from app.services.storage import LocalStorage
from app.tables import AppUser, AuditLog, FaceEmbedding, UserRole

EMAIL = "temp.replace.faces@unamba.edu.pe"


FRONTAL_KPS = np.array([[40, 45], [80, 45], [60, 65], [45, 85], [75, 85]], dtype=np.float32)


class FakeDetector:
    def detect(self, image, det_thresh=0.5, max_faces=1):
        return [SimpleNamespace(box=np.array([5, 5, 115, 115], dtype=np.float32), score=0.9, kps=FRONTAL_KPS)]


class FakeEmbedder:
    def __init__(self) -> None:
        self.calls = 0

    def get(self, image, kps):
        self.calls += 1
        vector = np.ones(512, dtype=np.float32)
        vector[self.calls % 512] += 0.5
        return vector / np.linalg.norm(vector)


def _photo() -> str:
    image = np.random.default_rng(1).integers(0, 255, (120, 120, 3), dtype=np.uint8)
    ok, buffer = cv2.imencode(".jpg", image)
    assert ok
    return "data:image/jpeg;base64," + base64.b64encode(buffer.tobytes()).decode()


@pytest.fixture
async def setup(db_session, tmp_path, monkeypatch):
    storage = LocalStorage(str(tmp_path))
    monkeypatch.setattr(faces, "get_storage", lambda: storage)
    monkeypatch.setattr(faces, "get_detector", lambda: FakeDetector())
    embedder = FakeEmbedder()
    monkeypatch.setattr(faces, "get_embedder", lambda: embedder)

    await db_session.exec(delete(AppUser).where(AppUser.email == EMAIL))
    await db_session.commit()
    student = AppUser(
        role=UserRole.ESTUDIANTE, email=EMAIL, code="990001", full_name="Estudiante Reemplazo",
        password_hash="x" * 20, must_change_password=False,
    )
    admin = (await db_session.exec(select(AppUser).where(AppUser.email == "admin@unamba.edu.pe"))).one()
    db_session.add(student)
    await db_session.commit()
    await db_session.refresh(student)
    yield SimpleNamespace(student=student, admin=admin, storage_dir=tmp_path)
    await db_session.exec(delete(FaceEmbedding).where(FaceEmbedding.student_id == student.id))
    await db_session.exec(delete(AuditLog).where(AuditLog.entity_id == student.id))
    await db_session.exec(delete(AppUser).where(AppUser.id == student.id))
    await db_session.commit()


async def _enroll(db_session, setup):
    return await faces.enrolar(
        db_session, setup.admin, setup.student.id, [_photo(), _photo(), _photo()], consent=True
    )


async def test_only_the_cover_photo_is_stored_per_enrollment(db_session, setup):
    await _enroll(db_session, setup)

    assert len(list(setup.storage_dir.iterdir())) == 1
    rows = (await db_session.exec(select(FaceEmbedding).where(FaceEmbedding.student_id == setup.student.id))).all()
    assert len(rows) == 1 and rows[0].is_current


async def test_reenrolling_removes_the_previous_photo_and_embedding(db_session, setup):
    await _enroll(db_session, setup)
    first_files = {path.name for path in setup.storage_dir.iterdir()}

    await _enroll(db_session, setup)

    second_files = {path.name for path in setup.storage_dir.iterdir()}
    assert len(second_files) == 1
    assert second_files.isdisjoint(first_files)
    rows = (await db_session.exec(select(FaceEmbedding).where(FaceEmbedding.student_id == setup.student.id))).all()
    assert len(rows) == 1 and rows[0].is_current


async def test_deleting_the_face_removes_the_stored_photo(db_session, setup):
    await _enroll(db_session, setup)

    result = await faces.eliminar_rostro(db_session, setup.admin, setup.student.id)

    assert result["deleted"] == 1
    assert list(setup.storage_dir.iterdir()) == []


def _rostro(box=(5, 5, 115, 115), score=0.9, kps=FRONTAL_KPS):
    return SimpleNamespace(box=np.array(box, dtype=np.float32), score=score, kps=np.array(kps, dtype=np.float32))


def _imagen_nitida() -> np.ndarray:
    return np.random.default_rng(3).integers(0, 255, (120, 120, 3), dtype=np.uint8)


def test_calidad_acepta_un_rostro_frontal_y_nitido():
    faces.validar_calidad(_imagen_nitida(), _rostro(), 1)


@pytest.mark.parametrize(
    ("rostro", "texto"),
    [
        (_rostro(box=(40, 40, 90, 90)), "muy pequeño"),
        (_rostro(score=0.4), "no se ve con claridad"),
        (_rostro(kps=[[40, 45], [80, 45], [78, 65], [45, 85], [75, 85]]), "de frente"),
        (_rostro(kps=[[40, 45], [80, 75], [60, 65], [45, 85], [75, 85]]), "cabeza derecha"),
    ],
)
def test_calidad_rechaza_fotos_deficientes(rostro, texto):
    with pytest.raises(faces.errors.DomainError, match=texto):
        faces.validar_calidad(_imagen_nitida(), rostro, 2)


def test_calidad_rechaza_fotos_borrosas():
    plana = np.full((120, 120, 3), 127, dtype=np.uint8)
    with pytest.raises(faces.errors.DomainError, match="borrosa"):
        faces.validar_calidad(plana, _rostro(), 1)


async def test_enrolar_nombra_la_cuenta_que_ya_tiene_ese_rostro(db_session, setup, monkeypatch):
    await _enroll(db_session, setup)
    otro = AppUser(
        role=UserRole.ESTUDIANTE, email="temp.replace.faces.otro@unamba.edu.pe", code="990002",
        full_name="Otra Cuenta", password_hash="x", is_active=True,
    )
    db_session.add(otro)
    await db_session.commit()
    await db_session.refresh(otro)
    otro_id = otro.id
    try:
        monkeypatch.setattr(faces, "get_embedder", lambda: SimpleNamespace(get=lambda image, kps: np.ones(512, dtype=np.float32) / np.sqrt(512)))
        with pytest.raises(faces.errors.ConflictError, match=r"Estudiante Reemplazo \(990001\)"):
            await faces.enrolar(db_session, setup.admin, otro_id, [_photo(), _photo(), _photo()], consent=True)
    finally:
        await db_session.exec(delete(AppUser).where(AppUser.id == otro_id))
        await db_session.commit()
