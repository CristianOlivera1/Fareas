import numpy as np
import pytest

from app.core.config import get_settings
from app.routers import pilot as pilot_router
from app.services import pilot

pytestmark = pytest.mark.asyncio

API = "/api/v1"


@pytest.fixture(autouse=True)
def pilot_file(tmp_path, monkeypatch):
    path = tmp_path / "pilot_data.csv"
    monkeypatch.setattr(get_settings(), "PILOT_DATA_FILE", str(path))
    return path


class FakeSource:
    def __init__(self):
        self.count = 0

    def read(self):
        self.count += 1
        return True, np.full((20, 20, 3), self.count % 250, dtype=np.uint8)

    def release(self):
        return None


class FakeFace:
    def __init__(self):
        self.box = np.array([0, 0, 100, 100], dtype=np.float32)
        self.score = 0.9
        self.kps = np.zeros((5, 2), dtype=np.float32)


class FakeDetector:
    def detect(self, frame, max_faces=5):
        return [FakeFace()]


class FakeEmbedder:
    def get(self, frame, kps):
        return np.ones(512, dtype=np.float32)


class FakeGallery:
    def best_similarities(self, embedding):
        return {1: 0.7, 2: 0.1}


def test_wilson_interval_for_zero_errors():
    low, high = pilot.wilson(0, 100)

    assert low == 0.0
    assert high == pytest.approx(0.037, abs=0.001)


def test_decision_requires_consecutive_frames_threshold_and_margin():
    strong = [{"scores": {"P01": 0.7, "P02": 0.1}}] * 3
    ambiguous = [{"scores": {"P01": 0.7, "P02": 0.68}}] * 3
    weak = [{"scores": {"P01": 0.4, "P02": 0.1}}] * 3

    assert pilot.decide(strong, 0.55, 0.06, 3) == "P01"
    assert pilot.decide(strong[:2], 0.55, 0.06, 3) is None
    assert pilot.decide(ambiguous, 0.55, 0.06, 3) is None
    assert pilot.decide(weak, 0.55, 0.06, 3) is None


def test_capture_logs_similarities_and_summary_counts_outcomes():
    aliases = {1: "P01", 2: "P02"}
    for alias, condition in (("P01", "normal"), ("P01", "adversa"), ("P02", "normal"), (pilot.NON_ENROLLED, "no_enrolado")):
        result = pilot.run_capture(FakeSource(), FakeDetector(), FakeEmbedder(), FakeGallery(), aliases, alias, condition, 1)
        assert result["frames"] >= 3

    summary = pilot.summarize(0.55, 0.06, 3)

    assert summary["captures"] == 4
    assert summary["unenrolled_captures"] == 1
    assert summary["per_alias"]["P01"] == {"normal": 1, "adversa": 1}
    assert summary["tar"]["count"] == 2 and summary["tar"]["total"] == 3
    assert summary["misidentified"]["count"] == 1
    assert summary["far"]["count"] == 1 and summary["far"]["total"] == 1


async def test_pilot_endpoints_require_admin(client):
    assert (await client.get(f"{API}/pilot/status")).status_code == 401
    assert (await client.post(f"{API}/pilot/captures", json={})).status_code == 401
    assert (await client.get(f"{API}/pilot/export")).status_code == 401


async def test_export_is_404_until_there_is_data(client, admin_login):
    response = await client.get(f"{API}/pilot/export", headers=admin_login["headers"])

    assert response.status_code == 404


async def test_status_lists_enrolled_students_and_empty_metrics(client, admin_login):
    response = await client.get(f"{API}/pilot/status", headers=admin_login["headers"])

    assert response.status_code == 200
    body = response.json()
    assert body["captures"] == 0
    assert body["tar"]["total"] == 0
    assert all({"id", "name", "alias", "normal", "adversa"} <= set(s) for s in body["students"])


async def test_capture_rejects_students_without_a_face_template(client, admin_login):
    response = await client.post(
        f"{API}/pilot/captures", json={"student_id": 987654321, "condition": "normal", "seconds": 3},
        headers=admin_login["headers"],
    )

    assert response.status_code in (404, 422)


async def test_capture_of_a_non_enrolled_person_is_stored_and_exported(client, admin_login, monkeypatch):
    status = await client.get(f"{API}/pilot/status", headers=admin_login["headers"])
    if status.json()["camera_room"] is None or not status.json()["students"]:
        pytest.skip("requiere una cámara activa y al menos un estudiante enrolado en la base")

    monkeypatch.setattr(pilot_router, "open_source", lambda url: FakeSource())
    monkeypatch.setattr(
        pilot_router.pilot, "run_capture",
        lambda *args, **kwargs: {"capture_id": "abc12345", "frames": 7, "alias": "NONE", "condition": "no_enrolado"},
    )
    response = await client.post(
        f"{API}/pilot/captures", json={"student_id": None, "seconds": 3}, headers=admin_login["headers"]
    )

    assert response.status_code == 201
    assert response.json() == {"capture_id": "abc12345", "frames": 7, "alias": "NONE", "condition": "no_enrolado"}
