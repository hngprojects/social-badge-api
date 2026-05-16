import asyncio
import logging
import uuid

import cloudinary  # type: ignore[import-untyped]
import cloudinary.uploader  # type: ignore[import-untyped]

from app.core.config import settings
from app.core.exceptions import CloudinaryUploadError

logger = logging.getLogger(__name__)


def _configure_cloudinary() -> None:
    if not all(
        [
            settings.CLOUDINARY_CLOUD_NAME,
            settings.CLOUDINARY_API_KEY,
            settings.CLOUDINARY_API_SECRET,
        ]
    ):
        raise CloudinaryUploadError(
            "Cloudinary credentials are not configured. "
            "Set CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, and CLOUDINARY_API_SECRET."
        )
    cloudinary.config(
        cloud_name=settings.CLOUDINARY_CLOUD_NAME,
        api_key=settings.CLOUDINARY_API_KEY,
        api_secret=settings.CLOUDINARY_API_SECRET,
        secure=True,
    )


def _upload_sync(data: bytes, filename: str) -> str:
    _configure_cloudinary()
    try:
        result = cloudinary.uploader.upload(
            data,
            public_id=filename,
            folder=settings.LOGO_FOLDER,
            resource_type="image",
            overwrite=True,
            invalidate=True,
        )
    except Exception as exc:
        raise CloudinaryUploadError(str(exc)) from exc
    url: str = result["secure_url"]
    return url


def _delete_sync(public_id: str) -> None:
    _configure_cloudinary()
    try:
        cloudinary.uploader.destroy(public_id, resource_type="image", invalidate=True)
    except Exception as exc:
        raise CloudinaryUploadError(str(exc)) from exc


async def upload_logo(data: bytes) -> tuple[str, str]:
    filename = str(uuid.uuid4())
    public_id = f"{settings.LOGO_FOLDER}/{filename}"
    url = await asyncio.to_thread(_upload_sync, data, filename)
    return url, public_id


async def delete_logo(public_id: str) -> None:
    await asyncio.to_thread(_delete_sync, public_id)
