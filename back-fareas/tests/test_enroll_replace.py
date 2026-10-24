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


class FakeDetector:
    def detect(self, image, det_thresh=0.5, max_faces=1):
        return [SimpleNamespace(kps=np.zeros((5, 2), dtype=np.float32))]


class FakeEmbedder:
    def __init__(self) -> None:
        self.calls = 0

    def get(self, image, kps):
        self.calls += 1
        vector = np.ones(512, dtype=np.float32)
        vector[self.calls % 512] += 0.5
        return vector / np.linalg.norm(vector)


def _photo() -> str:
    image = np.full((120, 120, 3), 127, dtype=np.uint8)
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
