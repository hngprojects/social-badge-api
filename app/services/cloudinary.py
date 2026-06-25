import asyncio
import logging
import uuid

import cloudinary  # type: ignore[import-untyped]
import cloudinary.uploader  # type: ignore[import-untyped]

from app.core.config import settings
from app.core.exceptions import CloudinaryUploadError

logger = logging.getLogger(__name__)


def _configure_cloudinary() -> None:
    """
    Initializes the Cloudinary client configuration settings.

    Verifies that all required Cloudinary API credentials exist in settings,
    and raises an exception if any credentials are missing.

    Raises:
        CloudinaryUploadError: If credentials are not properly configured.
    """
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
    """
    Uploads image bytes synchronously to Cloudinary.

    Configures Cloudinary credentials, uploads the binary payload,
    overwrites existing assets if the filename matches,
    and invalidates cached CDN versions. Returns the secure CDN URL.

    Raises:
        CloudinaryUploadError: If the upload operation fails.
    """
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
        url: str = result["secure_url"]
    except Exception as exc:
        raise CloudinaryUploadError(str(exc)) from exc
    return url


def _delete_sync(public_id: str) -> None:
    """
    Destroys a specified asset synchronously on Cloudinary.

    Initializes credentials, executes the destruction call, and invalidates CDN caches.

    Raises:
        CloudinaryUploadError: If the deletion API call fails.
    """
    _configure_cloudinary()
    try:
        cloudinary.uploader.destroy(public_id, resource_type="image", invalidate=True)
    except Exception as exc:
        raise CloudinaryUploadError(str(exc)) from exc


async def upload_logo(data: bytes) -> tuple[str, str]:
    """
    Asynchronously uploads a logo image to Cloudinary using a backgroun thread executor.

    Generates a unique random filename, performs a thread-safe synchronous upload,
    and returns a tuple containing the secure URL and the generated public ID.

    Raises:
        CloudinaryUploadError: If the upload fails.
    """
    filename = str(uuid.uuid4())
    public_id = f"{settings.LOGO_FOLDER}/{filename}"
    url = await asyncio.to_thread(_upload_sync, data, filename)
    return url, public_id


async def delete_logo(public_id: str) -> None:
    """
    Asynchronously deletes a logo from Cloudinary using a background thread executor.

    Raises:
        CloudinaryUploadError: If the delete operation fails.
    """
    await asyncio.to_thread(_delete_sync, public_id)


async def delete_asset(public_id: str) -> None:
    """
    Asynchronously deletes any Cloudinary asset using its public identifier
    in a background thread.

    Raises:
        CloudinaryUploadError: If the delete operation fails.
    """
    await asyncio.to_thread(_delete_sync, public_id)
