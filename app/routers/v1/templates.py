from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, File, HTTPException, Request, UploadFile, status

from app.core.exceptions import (
    CloudinaryUploadError,
    NotTemplateOwnerError,
    OrganiserTemplateNotFoundError,
    PlatformTemplateNotFoundError,
    TemplateAlreadyPublishedError,
    TemplateInstanceForbiddenError,
    TemplateInstanceNotFoundError,
)
from app.core.rate_limit import limiter
from app.dependencies import CurrentUser, DBSession
from app.schemas.response import ErrorResponse, SuccessResponse
from app.schemas.template import (
    CreateTemplateInstanceRequest,
    LogoUploadResponse,
    PublishedTemplateResponse,
    TemplateInstanceResponse,
)
from app.services.template import (
    create_template_instance,
    publish_template,
    unpublish_template,
    upload_template_logo,
)

router = APIRouter()

_MAX_LOGO_BYTES = 2 * 1024 * 1024  # 2 MB
_ALLOWED_CONTENT_TYPES = {"image/png", "image/jpeg"}

# Magic bytes for format verification (cannot be spoofed via Content-Type header).
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_JPEG_MAGIC = b"\xff\xd8\xff"


def _is_valid_image(data: bytes) -> bool:
    """Return True only if bytes start with a recognised PNG or JPEG signature."""
    return data[:8] == _PNG_MAGIC or data[:3] == _JPEG_MAGIC


@router.post(
    "/instances",
    response_model=SuccessResponse[TemplateInstanceResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create a new template instance from a platform template",
    description=(
        "Creates a new organiser template instance linked to the chosen "
        "platform template. The original platform template is never modified. "
        "The organiser is taken from the JWT, never from the request body."
    ),
    responses={
        201: {
            "description": "Template instance created.",
            "content": {
                "application/json": {
                    "example": {
                        "status": "success",
                        "message": "Template instance created successfully.",
                        "data": {
                            "instance_id": "019e1b66-c4ec-7b80-8c85-84c2fe4f9c84",
                            "platform_template_id": (
                                "019e1b66-c4ec-7b80-8c85-84c2fe4f9c00"
                            ),
                            "organiser_id": "019e1b66-c4ec-7b80-8c85-84c2fe4f9c11",
                            "created_at": "2026-05-12T09:30:00Z",
                        },
                    }
                }
            },
        },
        401: {"model": ErrorResponse, "description": "Unauthenticated."},
        404: {"model": ErrorResponse, "description": "Platform template not found."},
        422: {"model": ErrorResponse, "description": "Validation error."},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded."},
    },
)
@limiter.limit("30/minute")
async def create_instance(
    request: Request,
    session: DBSession,
    current_user: CurrentUser,
    payload: CreateTemplateInstanceRequest,
) -> SuccessResponse[TemplateInstanceResponse]:
    """Create a new organiser template instance from a platform template."""
    try:
        instance = await create_template_instance(
            session=session,
            organiser_id=current_user.id,
            platform_template_id=payload.platform_template_id,
        )
    except PlatformTemplateNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Platform template not found.",
        ) from exc

    assert instance.created_at is not None  # noqa: S101
    return SuccessResponse(
        message="Template instance created successfully.",
        data=TemplateInstanceResponse(
            instance_id=instance.id,
            platform_template_id=instance.platform_template_id,
            organiser_id=instance.organiser_id,
            created_at=instance.created_at,
        ),
    )


@router.post(
    "/{template_id}/publish",
    response_model=SuccessResponse[PublishedTemplateResponse],
    status_code=status.HTTP_200_OK,
    summary="Publish an organiser template",
    description=(
        "Publishes the organiser's template. Sets is_published to true, "
        "records the publish time, and generates a unique share slug on "
        "first publish. The slug is preserved across re-publishes."
    ),
    responses={
        200: {"description": "Template published."},
        401: {"model": ErrorResponse, "description": "Unauthenticated."},
        403: {"model": ErrorResponse, "description": "Not the template owner."},
        404: {"model": ErrorResponse, "description": "Template not found."},
        409: {"model": ErrorResponse, "description": "Template is already published."},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded."},
    },
)
@limiter.limit("30/minute")
async def publish(
    request: Request,
    session: DBSession,
    current_user: CurrentUser,
    template_id: UUID,
) -> SuccessResponse[PublishedTemplateResponse]:
    """Publish an organiser template."""
    try:
        template = await publish_template(
            session=session,
            organiser_id=current_user.id,
            template_id=template_id,
        )
    except OrganiserTemplateNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found.",
        ) from exc
    except NotTemplateOwnerError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not own this template.",
        ) from exc
    except TemplateAlreadyPublishedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Template is already published.",
        ) from exc

    return SuccessResponse(
        message="Template published successfully.",
        data=PublishedTemplateResponse.model_validate(template),
    )


@router.post(
    "/{template_id}/unpublish",
    response_model=SuccessResponse[PublishedTemplateResponse],
    status_code=status.HTTP_200_OK,
    summary="Unpublish an organiser template",
    description=(
        "Unpublishes the organiser's template. Sets is_published to false. "
        "The share slug is preserved so re-publishing later keeps the same URL."
    ),
    responses={
        200: {"description": "Template unpublished."},
        401: {"model": ErrorResponse, "description": "Unauthenticated."},
        403: {"model": ErrorResponse, "description": "Not the template owner."},
        404: {"model": ErrorResponse, "description": "Template not found."},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded."},
    },
)
@limiter.limit("30/minute")
async def unpublish(
    request: Request,
    session: DBSession,
    current_user: CurrentUser,
    template_id: UUID,
) -> SuccessResponse[PublishedTemplateResponse]:
    """Unpublish an organiser template."""
    try:
        template = await unpublish_template(
            session=session,
            organiser_id=current_user.id,
            template_id=template_id,
        )
    except OrganiserTemplateNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found.",
        ) from exc
    except NotTemplateOwnerError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not own this template.",
        ) from exc

    return SuccessResponse(
        message="Template unpublished successfully.",
        data=PublishedTemplateResponse.model_validate(template),
    )


@router.put(
    "/instances/{instance_id}/logo",
    response_model=SuccessResponse[LogoUploadResponse],
    status_code=status.HTTP_200_OK,
    summary="Upload a logo for a template instance",
    description=(
        "Accepts a multipart/form-data upload with a single PNG or JPG image "
        "(max 2 MB). Stores the file in Cloudinary under the template-logos/ "
        "folder and returns the resulting URL. If the instance already has a "
        "logo, the new file is uploaded and persisted first, then the old "
        "Cloudinary asset is deleted. "
        "The instance must belong to the authenticated organiser."
    ),
    responses={
        200: {
            "description": "Logo uploaded successfully.",
            "content": {
                "application/json": {
                    "example": {
                        "status": "success",
                        "message": "Logo uploaded successfully.",
                        "data": {
                            "logo_url": "https://res.cloudinary.com/demo/image/upload/template-logos/abc.png"
                        },
                    }
                }
            },
        },
        401: {"model": ErrorResponse, "description": "Unauthenticated."},
        403: {
            "model": ErrorResponse,
            "description": "Instance belongs to another organiser.",
        },
        404: {"model": ErrorResponse, "description": "Template instance not found."},
        413: {"model": ErrorResponse, "description": "File exceeds the 2 MB limit."},
        415: {
            "model": ErrorResponse,
            "description": "Unsupported file type (PNG and JPG only).",
        },
        429: {"model": ErrorResponse, "description": "Rate limit exceeded."},
    },
)
@limiter.limit("10/minute")
async def upload_logo(
    instance_id: UUID,
    request: Request,
    session: DBSession,
    current_user: CurrentUser,
    file: Annotated[UploadFile, File()],
) -> SuccessResponse[LogoUploadResponse]:
    """Upload or replace the logo for a template instance."""
    if file.content_type not in _ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Unsupported file type. Only PNG and JPG images are allowed.",
        )

    # Read one byte beyond the limit so we can detect oversized files without
    # loading an arbitrarily large upload into memory.
    image_data = await file.read(_MAX_LOGO_BYTES + 1)
    if len(image_data) > _MAX_LOGO_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="File size exceeds the 2 MB limit.",
        )

    # Verify the actual file signature — content_type is client-controlled.
    if not _is_valid_image(image_data):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Unsupported file type. Only PNG and JPG images are allowed.",
        )

    try:
        logo_url = await upload_template_logo(
            session=session,
            instance_id=instance_id,
            organiser_id=current_user.id,
            image_data=image_data,
        )
    except TemplateInstanceNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template instance not found.",
        ) from exc
    except TemplateInstanceForbiddenError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to modify this template instance.",
        ) from exc
    except CloudinaryUploadError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                "Logo upload failed. The upload service is unavailable"
                " or rejected the file."
            ),
        ) from exc

    return SuccessResponse(
        message="Logo uploaded successfully.",
        data=LogoUploadResponse(logo_url=logo_url),
    )
