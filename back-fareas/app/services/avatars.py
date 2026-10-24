import io
import logging

from PIL import Image, ImageOps, UnidentifiedImageError

from app.core.config import get_settings
from app.services.storage import avatar_key, get_storage

logger = logging.getLogger("fareas.avatars")

AVATAR_SIDE = 256
MAX_SOURCE_PIXELS = 25_000_000
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}


class InvalidAvatarError(ValueError):
    pass


def normalize_avatar(data: bytes) -> bytes:
    try:
        with Image.open(io.BytesIO(data)) as source:
            if source.format not in ALLOWED_FORMATS:
                raise InvalidAvatarError("La foto debe ser JPG, PNG o WEBP")
            if source.width * source.height > MAX_SOURCE_PIXELS:
                raise InvalidAvatarError("La imagen es demasiado grande; usa una de menor resolución")
            image = ImageOps.exif_transpose(source).convert("RGB")
    except UnidentifiedImageError as exc:
        raise InvalidAvatarError("El archivo no es una imagen válida") from exc
    except OSError as exc:
        raise InvalidAvatarError("No se pudo leer la imagen") from exc

    square = ImageOps.fit(image, (AVATAR_SIDE, AVATAR_SIDE), method=Image.Resampling.LANCZOS)
    output = io.BytesIO()
    square.save(output, format="JPEG", quality=85, optimize=True)
    return output.getvalue()


def max_upload_bytes() -> int:
    return get_settings().AVATAR_MAX_UPLOAD_MB * 1024 * 1024


async def store_avatar(user_id: int, data: bytes) -> str:
    return await get_storage().put(avatar_key(user_id), normalize_avatar(data), "image/jpeg")


async def delete_avatar(key: str | None) -> None:
    if not key:
        return
    try:
        await get_storage().delete(key)
    except Exception:
        logger.warning("No se pudo borrar la foto de perfil %s", key, exc_info=True)


async def avatar_url(key: str | None) -> str | None:
    if not key:
        return None
    return await get_storage().url(key, get_settings().AVATAR_URL_EXPIRE_SECONDS)
