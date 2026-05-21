from typing import Annotated
from urllib.parse import urlencode
from uuid import UUID

from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile, status

from app.core.exceptions import (
    CloudinaryUploadError,
    NotTemplateOwnerError,
    OrganiserTemplateNotFoundError,
    PlatformTemplateNotFoundError,
    PublicTemplateNotFoundError,
    TemplateAlreadyPublishedError,
    TemplateInstanceForbiddenError,
    TemplateInstanceNotFoundError,
)
from app.core.rate_limit import limiter
from app.dependencies import CurrentUser, DBSession
from app.schemas.response import ErrorResponse, SuccessResponse
from app.schemas.template import (
    CreateTemplateInstanceRequest,
    DuplicateTemplateResponse,
    LogoUploadResponse,
    OrganiserTemplateListResponse,
    OrganiserTemplateSummary,
    PlatformTemplateListResponse,
    PlatformTemplateResponse,
    PublicParticipantPageResponse,
    PublishedTemplateResponse,
    TemplateInstanceResponse,
)
from app.services.template import (
    create_template_instance,
    delete_organiser_template,
    duplicate_template,
    get_platform_template,
    get_public_template_by_slug,
    list_organiser_templates,
    list_platform_templates,
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
    "/organizer/instances",
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


@router.get(
    "/organizer/instances",
    response_model=SuccessResponse[OrganiserTemplateListResponse],
    status_code=status.HTTP_200_OK,
    summary="List organiser template instances",
    description=(
        "Returns a paginated list of all template instances owned by the "
        "authenticated organiser. Soft-deleted templates are excluded. "
        "Each item includes a computed status field ('draft' or 'published'). "
        "Results are ordered by most recently updated first."
    ),
    responses={
        200: {
            "description": "Template instances retrieved successfully.",
            "content": {
                "application/json": {
                    "example": {
                        "status": "success",
                        "message": "Template instances retrieved successfully.",
                        "data": {
                            "templates": [
                                {
                                    "id": "019e1b66-c4...fe4f9c84",
                                    "title": "HNG Tech Fest 2026",
                                    "platform_template_id": "019e1b66-c4...fe4f9c00",
                                    "thumbnail_url": None,
                                    "is_published": True,
                                    "status": "published",
                                    "share_slug": "abcdef123456",
                                    "published_at": "2026-05-20T10:00:00Z",
                                    "created_at": "2026-05-18T09:00:00Z",
                                    "updated_at": "2026-05-20T10:00:00Z",
                                }
                            ],
                            "total": 1,
                            "page": 1,
                            "limit": 20,
                            "prev": None,
                            "next": None,
                        },
                    }
                }
            },
        },
        401: {"model": ErrorResponse, "description": "Unauthenticated."},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded."},
    },
)
@limiter.limit("60/minute")
async def list_instances(
    request: Request,
    session: DBSession,
    current_user: CurrentUser,
    page: int = Query(default=1, ge=1, description="Page number (1-based)."),
    limit: int = Query(default=20, ge=1, le=100, description="Items per page."),
) -> SuccessResponse[OrganiserTemplateListResponse]:
    """Return paginated template instances for the authenticated organiser."""
    templates, total = await list_organiser_templates(
        session=session,
        organiser_id=current_user.id,
        page=page,
        limit=limit,
    )

    base_url = "/api/v1/templates/organizer/instances"

    prev_link = None
    if page > 1:
        prev_link = f"{base_url}?page={page - 1}&limit={limit}"

    next_link = None
    if page * limit < total:
        next_link = f"{base_url}?page={page + 1}&limit={limit}"

    return SuccessResponse(
        message="Template instances retrieved successfully.",
        data=OrganiserTemplateListResponse(
            templates=[
                OrganiserTemplateSummary.model_validate(org_template)
                for org_template in templates
            ],
            total=total,
            page=page,
            limit=limit,
            prev=prev_link,
            next=next_link,
        ),
    )


@router.post(
    "/organizer/{template_id}/publish",
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
    "/organizer/{template_id}/unpublish",
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


@router.post(
    "/organizer/{template_id}/duplicate",
    response_model=SuccessResponse[DuplicateTemplateResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Duplicate an organiser template",
    description=(
        "Creates a draft copy of the organiser's template. "
        "The copy receives a new unique ID, inherits all configuration "
        "fields and hashtags from the original, and starts in an unpublished state. "
        "The original template is not modified."
    ),
    responses={
        201: {"description": "Draft copy created."},
        401: {"model": ErrorResponse, "description": "Unauthenticated."},
        403: {"model": ErrorResponse, "description": "Not the template owner."},
        404: {"model": ErrorResponse, "description": "Template not found."},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded."},
    },
)
@limiter.limit("30/minute")
async def duplicate(
    request: Request,
    session: DBSession,
    current_user: CurrentUser,
    template_id: UUID,
) -> SuccessResponse[DuplicateTemplateResponse]:
    """Duplicate an organiser template into a new draft."""
    try:
        copy = await duplicate_template(
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
        message="Template duplicated successfully.",
        data=DuplicateTemplateResponse.model_validate(copy),
    )


@router.delete(
    "/organizer/{template_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an organiser template",
    description=(
        "Permanently removes the organiser template and all associated records "
        "(badges, hashtags) from the database. The Cloudinary logo and any "
        "generated badge image assets are also deleted on a best-effort basis — "
        "a Cloudinary failure does not cause the request to fail. "
        "This action is irreversible."
    ),
    responses={
        204: {"description": "Template deleted successfully."},
        401: {"model": ErrorResponse, "description": "Unauthenticated."},
        403: {"model": ErrorResponse, "description": "Not the template owner."},
        404: {"model": ErrorResponse, "description": "Template not found."},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded."},
    },
)
@limiter.limit("30/minute")
async def delete_template(
    request: Request,
    session: DBSession,
    current_user: CurrentUser,
    template_id: UUID,
) -> None:
    """Permanently delete an organiser template and its Cloudinary assets."""
    try:
        await delete_organiser_template(
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


@router.put(
    "/organizer/instances/{instance_id}/logo",
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


@router.get(
    "/organizer/public/{slug}",
    response_model=SuccessResponse[PublicParticipantPageResponse],
    status_code=status.HTTP_200_OK,
    summary="Get public participant page data",
    description=(
        "Returns the public-facing template data needed to render the participant "
        "page. No authentication required. Only returns data for published "
        "templates — unpublished slugs return 404. Exposes only the fields "
        "needed for public rendering, not organiser configuration internals."
    ),
    responses={
        200: {
            "description": "Published template data.",
            "content": {
                "application/json": {
                    "example": {
                        "status": "success",
                        "message": "Template data retrieved successfully.",
                        "data": {
                            "title": "HNG Tech Fest 2026",
                            "canvas_data": {"layout": "bold-v1"},
                            "logo_url": "https://res.cloudinary.com/demo/image/upload/template-logos/abc.png",
                            "default_caption": "I'm attending HNG Tech Fest 2026!",
                            "destination_link": "https://techfest.example.com",
                            "hashtags": ["#HNGTechFest", "#2026"],
                        },
                    }
                }
            },
        },
        404: {
            "model": ErrorResponse,
            "description": "Slug not found or template is not published.",
        },
        429: {"model": ErrorResponse, "description": "Rate limit exceeded."},
    },
)
@limiter.limit("60/minute")
async def get_participant_page(
    request: Request,
    session: DBSession,
    slug: str,
) -> SuccessResponse[PublicParticipantPageResponse]:
    """Return public-facing template data for the participant page."""
    try:
        template = await get_public_template_by_slug(
            session=session,
            slug=slug,
        )
    except PublicTemplateNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found.",
        ) from exc

    return SuccessResponse(
        message="Template data retrieved successfully.",
        data=PublicParticipantPageResponse(
            title=template.title,
            canvas_data=template.canvas_data,
            logo_url=template.logo_url,
            default_caption=template.default_caption,
            destination_link=template.destination_link,
            hashtags=[h.hashtag for h in template.hashtags],
        ),
    )


@router.get(
    "/platform",
    response_model=SuccessResponse[PlatformTemplateListResponse],
    status_code=status.HTTP_200_OK,
    summary="List platform templates (gallery)",
    description=(
        "Returns all active platform templates. Pass `?category=` to filter by "
        "gallery tab. No authentication required. "
        "Valid categories: festivals, hackathons, conferences, community, "
        "bootcamp, meetups, speakers, trending."
    ),
    responses={
        200: {
            "description": "Templates retrieved successfully.",
            "content": {
                "application/json": {
                    "example": {
                        "status": "success",
                        "message": "Platform templates retrieved successfully.",
                        "data": {
                            "templates": [
                                {
                                    "id": "019e1b66-c4ec-7b80-8c85-84c2fe4f9c84",
                                    "title": "Achieveher",
                                    "category": "festivals",
                                    "thumbnail_url": None,
                                    "canvas_data": {"layout_id": "photo_gradient_v1"},
                                    "is_active": True,
                                    "created_at": "2026-05-18T12:00:00Z",
                                }
                            ],
                            "total": 1,
                            "page": 1,
                            "limit": 10,
                            "prev": None,
                            "next": None,
                        },
                    }
                }
            },
        },
        400: {
            "model": ErrorResponse,
            "description": "Unknown category value.",
        },
        422: {
            "model": ErrorResponse,
            "description": "Validation error on query parameters.",
        },
        429: {"model": ErrorResponse, "description": "Rate limit exceeded."},
    },
)
@limiter.limit("60/minute")
async def list_templates(
    request: Request,
    session: DBSession,
    category: str | None = Query(
        default=None,
        description=(
            "Gallery tab filter. One of: festivals, hackathons, conferences, "
            "community, bootcamp, meetups, speakers, trending."
        ),
        examples=["festivals"],
    ),
    page: int = Query(
        default=1,
        ge=1,
        description="Page number (1-based)",
    ),
    limit: int = Query(
        default=10,
        ge=1,
        le=100,
        description="Items per page",
    ),
) -> SuccessResponse[PlatformTemplateListResponse]:
    """Return active platform templates with pagination and optional category filter."""
    normalised_category = category.strip().lower() if category is not None else None
    try:
        templates, total = await list_platform_templates(
            session, category=normalised_category, page=page, limit=limit
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    base_url = "/api/v1/templates/platform"
    query_params: dict[str, str | int] = {"limit": limit}
    if normalised_category:
        query_params["category"] = normalised_category

    prev_link = None
    if page > 1:
        prev_link = f"{base_url}?{urlencode({'page': page - 1, **query_params})}"

    next_link = None
    if page * limit < total:
        next_link = f"{base_url}?{urlencode({'page': page + 1, **query_params})}"

    return SuccessResponse(
        message="Platform templates retrieved successfully.",
        data=PlatformTemplateListResponse(
            templates=[PlatformTemplateResponse.model_validate(t) for t in templates],
            total=total,
            page=page,
            limit=limit,
            prev=prev_link,
            next=next_link,
        ),
    )


@router.get(
    "/platform/{template_id}",
    response_model=SuccessResponse[PlatformTemplateResponse],
    status_code=status.HTTP_200_OK,
    summary="Get a single platform template",
    description=(
        "Returns the full platform template detail, including canvas_data. "
        "Used to populate the live preview panel when an organiser clicks a "
        "gallery card. No authentication required."
    ),
    responses={
        200: {"description": "Platform template retrieved successfully."},
        404: {
            "model": ErrorResponse,
            "description": "Platform template not found or inactive.",
        },
        422: {
            "model": ErrorResponse,
            "description": "Validation error on query parameters.",
        },
        429: {"model": ErrorResponse, "description": "Rate limit exceeded."},
    },
)
@limiter.limit("60/minute")
async def get_template(
    request: Request,
    session: DBSession,
    template_id: UUID,
) -> SuccessResponse[PlatformTemplateResponse]:
    """Return a single active platform template by id."""
    try:
        template = await get_platform_template(session, template_id)
    except PlatformTemplateNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Platform template not found.",
        ) from exc

    return SuccessResponse(
        message="Platform template retrieved successfully.",
        data=PlatformTemplateResponse.model_validate(template),
    )
