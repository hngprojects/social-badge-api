from __future__ import annotations

from PIL import Image

_ALLOWED_PHOTO_TYPES: frozenset[str] = frozenset(
    {"image/jpeg", "image/png", "image/webp"}
)
_MAX_PHOTO_BYTES: int = 5 * 1024 * 1024
_MAX_FETCH_BYTES: int = 5 * 1024 * 1024
_MAX_DIMENSION: int = 8000  # px on either axis

_NORMALISED_TYPES: dict[str, str] = {
    "image/jpg": "image/jpeg",
    "image/pjpeg": "image/jpeg",
}


def normalise_content_type(content_type: str) -> str:
    """Normalise a declared MIME type to its canonical form.

    Strips MIME parameters (e.g. ``; charset=binary``) before lookup so that
    values like ``image/jpeg; charset=binary`` resolve correctly.
    """
    base = content_type.split(";", 1)[0].lower().strip()
    return _NORMALISED_TYPES.get(base, base)


def sniff_mime(data: bytes) -> str | None:
    """Return the MIME type inferred from magic bytes, or None if unrecognised."""
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def validate_image_dimensions(img: Image.Image) -> None:
    """Raise ValueError if either dimension exceeds _MAX_DIMENSION.

    Must be called after img.load() so that width/height are fully resolved.
    """
    if img.width > _MAX_DIMENSION or img.height > _MAX_DIMENSION:
        raise ValueError(
            f"Image dimensions {img.width}×{img.height} exceed the maximum "
            f"allowed {_MAX_DIMENSION}px on either side."
        )
