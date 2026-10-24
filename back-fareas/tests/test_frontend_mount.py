import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.frontend import mount_frontend, resolve_dist_dir


@pytest.fixture
def dist(tmp_path):
    (tmp_path / "index.html").write_text("<app-root>spa</app-root>", encoding="utf-8")
    (tmp_path / "main.js").write_text("console.log('bundle')", encoding="utf-8")
    return tmp_path


@pytest.fixture
async def spa(dist):
    app = FastAPI()

    @app.get("/api/v1/ping")
    async def ping() -> dict:
        return {"ok": True}

    mount_frontend(app, dist, ("api/v1", "docs"))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


async def test_serves_static_files(spa):
    r = await spa.get("/main.js")
    assert r.status_code == 200
    assert "bundle" in r.text


async def test_unknown_routes_fall_back_to_index(spa):
    r = await spa.get("/admin/courses/3")
    assert r.status_code == 200
    assert "spa" in r.text


async def test_api_routes_keep_working_and_unknown_api_paths_404(spa):
    assert (await spa.get("/api/v1/ping")).json() == {"ok": True}
    r = await spa.get("/api/v1/nope")
    assert r.status_code == 404
    assert "spa" not in r.text


async def test_path_traversal_does_not_leak_files(spa, dist):
    (dist.parent / "secret.txt").write_text("secret", encoding="utf-8")
    r = await spa.get("/..%2Fsecret.txt")
    assert "secret" not in r.text


def test_resolve_dist_dir(dist, tmp_path):
    assert resolve_dist_dir("") is None
    assert resolve_dist_dir(str(dist)) == dist.resolve()
    assert resolve_dist_dir(str(tmp_path / "missing")) is None
