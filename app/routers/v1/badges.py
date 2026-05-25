from fastapi import APIRouter, Form, HTTPException, Request, UploadFile, status

from app.core.rate_limit import limiter
from app.schemas.badge import (
    BadgeJobEnqueueData,
    BadgeJobStatusData,
    PhotoUploadData,
)
from app.schemas.response import SuccessResponse
from app.utils.media import (
    _ALLOWED_PHOTO_TYPES,
    normalise_content_type,
    sniff_mime,
)

router = APIRouter()


async def _read_and_validate_photo(file: UploadFile, max_bytes: int) -> bytes:
    """Read and validate an uploaded photo.

    Checks file size, detects MIME type from magic bytes, validates that the
    declared content-type matches the detected type, and confirms it is an
    allowed type.

    Returns the raw bytes on success; raises HTTPException on any failure.
    """
    data = await file.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Photo must not exceed 5 MB.",
        )

    detected = sniff_mime(data)
    if detected is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported file type. Only JPEG, PNG, and WEBP are accepted.",
        )

    declared = normalise_content_type(file.content_type or "")
    if detected != declared:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File content does not match declared content type.",
        )

    if detected not in _ALLOWED_PHOTO_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported file type. Only JPEG, PNG, and WEBP are accepted.",
        )

    return data


@router.post(
    "/upload-photo",
    response_model=SuccessResponse[PhotoUploadData],
    status_code=status.HTTP_200_OK,
)
@limiter.limit("20/minute")
async def upload_photo_endpoint(
    request: Request,
    photo: UploadFile,
) -> SuccessResponse[PhotoUploadData]:
    # Implemented in commit 6 (after Engineer A's renderer commits are merged).
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED)


@router.post(
    "/generate/{slug}",
    response_model=SuccessResponse[BadgeJobEnqueueData],
    status_code=status.HTTP_202_ACCEPTED,
)
@limiter.limit("10/minute")
async def generate_badge_endpoint(
    request: Request,
    slug: str,
    name: str = Form(..., max_length=100),
    photo: UploadFile | None = None,
    photo_public_id: str | None = Form(default=None),
) -> SuccessResponse[BadgeJobEnqueueData]:
    # Implemented in commit 7 (after commits 5, 6, and 8 are merged).
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED)


@router.get(
    "/job/{job_id}",
    response_model=SuccessResponse[BadgeJobStatusData],
    status_code=status.HTTP_200_OK,
)
async def get_job_status_endpoint(
    job_id: str,
) -> SuccessResponse[BadgeJobStatusData]:
    # Implemented in commit 7 (after commits 5, 6, and 8 are merged).
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED)
