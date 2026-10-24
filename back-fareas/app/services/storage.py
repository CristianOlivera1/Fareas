import asyncio
import uuid
from functools import lru_cache
from pathlib import Path

import boto3
from botocore.config import Config

from app.core.config import Settings, get_settings

_FACE_EXTENSIONS = {".jpg", ".jpeg", ".png"}
_DOCUMENT_EXTENSIONS = {".pdf", ".jpg", ".png"}
_DOCUMENT_SIGNATURES = (
    (b"%PDF-", "application/pdf", ".pdf"),
    (b"\xff\xd8\xff", "image/jpeg", ".jpg"),
    (b"\x89PNG\r\n\x1a\n", "image/png", ".png"),
)


def face_key(student_id: int, extension: str = ".jpg") -> str:
    ext = extension.lower()
    if ext not in _FACE_EXTENSIONS:
        ext = ".jpg"
    return f"students/{student_id}/faces/{uuid.uuid4().hex}{ext}"


def justification_key(justification_id: int, extension: str) -> str:
    ext = extension.lower()
    if ext not in _DOCUMENT_EXTENSIONS:
        ext = ".pdf"
    return f"justifications/{justification_id}/{uuid.uuid4().hex}{ext}"


def avatar_key(user_id: int) -> str:
    return f"avatars/{user_id}/{uuid.uuid4().hex}.jpg"


def detect_document_type(data: bytes) -> tuple[str, str] | None:
    for signature, content_type, extension in _DOCUMENT_SIGNATURES:
        if data.startswith(signature):
            return content_type, extension
    return None


def _is_external(key: str) -> bool:
    return key.startswith("storage/") or key.startswith("http://") or key.startswith("https://")


class LocalStorage:
    def __init__(self, root: str = "storage") -> None:
        self.root = Path(root)

    async def put(self, key: str, data: bytes, content_type: str) -> str:
        name = Path(key).name
        path = self.root / name
        await asyncio.to_thread(path.parent.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(path.write_bytes, data)
        return f"storage/{name}"

    async def delete(self, key: str) -> None:
        path = self.root / Path(key).name
        if path.exists():
            await asyncio.to_thread(path.unlink)

    async def url(self, key: str | None, expires: int | None = None) -> str | None:
        return key


class R2Storage:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        endpoint = settings.R2_ENDPOINT_URL or (
            f"https://{settings.R2_ACCOUNT_ID}.r2.cloudflarestorage.com"
        )
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=settings.R2_ACCESS_KEY_ID,
            aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
            region_name=settings.R2_REGION,
            config=Config(signature_version="s3v4", retries={"max_attempts": 2, "mode": "standard"}),
        )

    async def put(self, key: str, data: bytes, content_type: str) -> str:
        await asyncio.to_thread(
            self._client.put_object,
            Bucket=self.settings.R2_BUCKET_NAME,
            Key=key,
            Body=data,
            ContentType=content_type,
        )
        return key

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(
            self._client.delete_object,
            Bucket=self.settings.R2_BUCKET_NAME,
            Key=key,
        )

    async def url(self, key: str | None, expires: int | None = None) -> str | None:
        if not key or _is_external(key):
            return key
        return await asyncio.to_thread(
            self._client.generate_presigned_url,
            "get_object",
            Params={"Bucket": self.settings.R2_BUCKET_NAME, "Key": key},
            ExpiresIn=expires or self.settings.R2_PRESIGN_EXPIRE_SECONDS,
        )


Storage = LocalStorage | R2Storage


@lru_cache(maxsize=1)
def get_storage() -> Storage:
    settings = get_settings()
    if settings.R2_ENABLED and settings.R2_ACCESS_KEY_ID and settings.R2_SECRET_ACCESS_KEY:
        return R2Storage(settings)
    return LocalStorage()
