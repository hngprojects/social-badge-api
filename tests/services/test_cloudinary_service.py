"""End-to-end tests for cloudinary_service.py.

These tests hit the real Cloudinary API and are skipped automatically when
CLOUDINARY_CLOUD_NAME is not set (e.g. local dev without credentials, CI).

To run them locally:
    CLOUDINARY_CLOUD_NAME=... CLOUDINARY_API_KEY=... CLOUDINARY_API_SECRET=... \
        uv run pytest tests/services/test_cloudinary_service.py -v
"""

import pytest

from app.core.config import settings
from app.core.exceptions import CloudinaryUploadError
from app.services.cloudinary import (
    delete_logo,
    upload_logo,
)

pytestmark = pytest.mark.skipif(
    not (
        settings.CLOUDINARY_CLOUD_NAME
        and settings.CLOUDINARY_API_KEY
        and settings.CLOUDINARY_API_SECRET
        and settings.CLOUDINARY_API_KEY != "your_api_key_here"
    ),
    reason=(
        "Cloudinary credentials not configured — set CLOUDINARY_CLOUD_NAME, "
        "CLOUDINARY_API_KEY, and CLOUDINARY_API_SECRET to run"
    ),
)

# Minimal valid 1×1 PNG (67 bytes, base64-decoded).
_TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
    b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)


async def test_upload_logo_returns_url_and_public_id() -> None:
    """upload_logo should return a non-empty HTTPS URL and a public_id."""
    url, public_id = await upload_logo(_TINY_PNG)

    assert url.startswith("https://"), f"Expected HTTPS URL, got: {url}"
    assert "template-logos" in public_id
    assert public_id  # non-empty

    # Clean up the test asset so we don't leave orphans in Cloudinary.
    await delete_logo(public_id)


async def test_upload_logo_public_id_is_unique() -> None:
    """Two consecutive uploads of the same bytes should produce different public_ids."""
    _, public_id1 = await upload_logo(_TINY_PNG)
    _, public_id2 = await upload_logo(_TINY_PNG)

    assert public_id1 != public_id2

    await delete_logo(public_id1)
    await delete_logo(public_id2)


async def test_delete_logo_removes_asset() -> None:
    """delete_logo should not raise even when called on a freshly uploaded asset."""
    _, public_id = await upload_logo(_TINY_PNG)

    # Should complete without raising CloudinaryUploadError.
    await delete_logo(public_id)


async def test_upload_logo_invalid_data_raises() -> None:
    """Passing garbage bytes that Cloudinary rejects should raise
    CloudinaryUploadError."""
    with pytest.raises(CloudinaryUploadError):
        await upload_logo(b"this-is-not-an-image")
