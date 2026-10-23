from types import SimpleNamespace

from app.services import storage as storage_service


def _settings(**overrides) -> SimpleNamespace:
    base = {
        "R2_ENABLED": True,
        "R2_ACCOUNT_ID": "account",
        "R2_BUCKET_NAME": "fareas-assets",
        "R2_ENDPOINT_URL": "",
        "R2_REGION": "auto",
        "R2_ACCESS_KEY_ID": "key",
        "R2_SECRET_ACCESS_KEY": "secret",
        "R2_PRESIGN_EXPIRE_SECONDS": 900,
        "R2_MAX_UPLOAD_MB": 10,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_face_key_formats_and_sanitizes():
    key = storage_service.face_key(7, ".png")
    assert key.startswith("students/7/faces/")
    assert key.endswith(".png")
    assert storage_service.face_key(7, ".exe").endswith(".jpg")


async def test_local_storage_roundtrip(tmp_path):
    local = storage_service.LocalStorage(str(tmp_path))
    key = await local.put("students/1/faces/abc.jpg", b"data", "image/jpeg")
    assert key == "storage/abc.jpg"
    assert (tmp_path / "abc.jpg").read_bytes() == b"data"
    assert await local.url(key) == key
    await local.delete(key)
    assert not (tmp_path / "abc.jpg").exists()


async def test_r2_storage_uses_bucket_and_presign(monkeypatch):
    calls = []

    class FakeClient:
        def put_object(self, **kwargs):
            calls.append(("put", kwargs))

        def delete_object(self, **kwargs):
            calls.append(("delete", kwargs))

        def generate_presigned_url(self, operation, **kwargs):
            calls.append(("url", operation, kwargs))
            return "https://signed.example/" + kwargs["Params"]["Key"]

    monkeypatch.setattr(storage_service.boto3, "client", lambda *args, **kwargs: FakeClient())

    r2 = storage_service.R2Storage(_settings())
    key = "students/3/faces/abc.jpg"
    assert await r2.put(key, b"data", "image/jpeg") == key
    assert calls[0][1]["Bucket"] == "fareas-assets"
    assert await r2.url(key) == "https://signed.example/" + key
    assert calls[1][2]["ExpiresIn"] == 900
    await r2.delete(key)
    assert calls[2][0] == "delete"


async def test_r2_storage_keeps_legacy_storage_paths(monkeypatch):
    monkeypatch.setattr(storage_service.boto3, "client", lambda *args, **kwargs: object())
    r2 = storage_service.R2Storage(_settings())
    assert await r2.url("storage/foto.jpg") == "storage/foto.jpg"
    assert await r2.url(None) is None


def test_get_storage_falls_back_to_local(monkeypatch):
    monkeypatch.setattr(
        storage_service,
        "get_settings",
        lambda: _settings(R2_ENABLED=False, R2_ACCESS_KEY_ID="", R2_SECRET_ACCESS_KEY=""),
    )
    storage_service.get_storage.cache_clear()
    assert isinstance(storage_service.get_storage(), storage_service.LocalStorage)
    storage_service.get_storage.cache_clear()
