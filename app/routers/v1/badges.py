import logging
from typing import Annotated
from uuid import UUID

from fastapi import (
    APIRouter,
    BackgroundTasks,
    File,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)

from app.core.exceptions import (
    BadgeAlreadyPublishedError,
    BadgeNotFoundError,
    CloudinaryUploadError,
    NotBadgeOwnerError,
    PlatformTemplateNotActiveError,
    PlatformTemplateNotFoundError,
    PublicBadgeNotFoundError,
)
from app.core.rate_limit import limiter
from app.dependencies import CurrentUser, DBSession
from app.schemas.badge import (
    BadgeAnalyticsResponse,
    BadgeDetailResponse,
    BadgeListResponse,
    BadgeSummary,
    CreateBadgeRequest,
    CreateBadgeResponse,
    DuplicateBadgeResponse,
    EditBadgeRequest,
    LogoUploadResponse,
    PlatformTemplateUsage,
    PublicBadgePageResponse,
    PublishedBadgeResponse,
    ValidateAccessRequest,
)
from app.schemas.response import ErrorResponse, SuccessResponse
from app.services.badge import (
    create_badge,
    delete_badge,
    duplicate_badge,
    edit_badge,
    get_badge_analytics,
    get_badge_by_id,
    get_public_badge_by_slug,
    increment_badge_creation_count,
    increment_badge_share_count,
    list_badges,
    publish_badge,
    unpublish_badge,
    upload_badge_logo,
)

logger = logging.getLogger(__name__)

router = APIRouter()

_MAX_LOGO_BYTES = 2 * 1024 * 1024  # 2 MB
_ALLOWED_CONTENT_TYPES = {"image/png", "image/jpeg", "image/svg+xml"}

# Magic bytes for format verification (cannot be spoofed via Content-Type header).
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_JPEG_MAGIC = b"\xff\xd8\xff"


def _is_valid_image(data: bytes) -> bool:
    """Return True only if bytes start with a recognised PNG, JPEG, or SVG signature."""
    if data[:8] == _PNG_MAGIC or data[:3] == _JPEG_MAGIC:
        return True

    stripped_data = data.lstrip()
    return stripped_data.startswith(b"<?xml") or stripped_data.startswith(b"<svg")


@router.post(
    "",
    response_model=SuccessResponse[CreateBadgeResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create a new badge from a platform template",
    description=(
        "Creates a new organiser badge linked to the chosen "
        "platform template. The original platform template is never modified. "
        "The organiser is taken from the JWT, never from the request body."
    ),
    responses={
        201: {
            "description": "Badge created.",
            "content": {
                "application/json": {
                    "example": {
                        "status": "success",
                        "message": "Badge created successfully.",
                        "data": {
                            "id": "019e1b66-c4ec-7b80-8c85-84c2fe4f9c84",
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
        400: {
            "model": ErrorResponse,
            "description": "Platform template is not active.",
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
    payload: CreateBadgeRequest,
) -> SuccessResponse[CreateBadgeResponse]:
    """Create a new organiser badge from a platform template."""
    try:
        instance = await create_badge(
            session=session,
            organiser_id=current_user.id,
            platform_template_id=payload.platform_template_id,
        )
    except PlatformTemplateNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Platform template not found.",
        ) from exc
    except PlatformTemplateNotActiveError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Platform template is not active.",
        ) from exc

    assert instance.created_at is not None  # noqa: S101
    return SuccessResponse(
        message="Badge created successfully.",
        data=CreateBadgeResponse(
            id=instance.id,
            platform_template_id=instance.platform_template_id,
            organiser_id=instance.organiser_id,
            created_at=instance.created_at,
        ),
    )


@router.get(
    "",
    response_model=SuccessResponse[BadgeListResponse],
    status_code=status.HTTP_200_OK,
    summary="List organiser badges",
    description=(
        "Returns a paginated list of all badges owned by the "
        "authenticated organiser. Soft-deleted badges are excluded. "
        "Each item includes a computed status field ('draft' or 'published'). "
        "Results are ordered by most recently updated first."
    ),
    responses={
        200: {
            "description": "Badges retrieved successfully.",
            "content": {
                "application/json": {
                    "example": {
                        "status": "success",
                        "message": "Badges retrieved successfully.",
                        "data": {
                            "badges": [
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
                                    "total_shares": 42,
                                    "total_badges_created": 7,
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
) -> SuccessResponse[BadgeListResponse]:
    """Return paginated badges for the authenticated organiser."""
    badges, total = await list_badges(
        session=session,
        organiser_id=current_user.id,
        page=page,
        limit=limit,
    )

    base_url = "/api/v1/badges"

    prev_link = None
    if page > 1:
        prev_link = f"{base_url}?page={page - 1}&limit={limit}"

    next_link = None
    if page * limit < total:
        next_link = f"{base_url}?page={page + 1}&limit={limit}"

    return SuccessResponse(
        message="Badges retrieved successfully.",
        data=BadgeListResponse(
            badges=[BadgeSummary.model_validate(org_badge) for org_badge in badges],
            total=total,
            page=page,
            limit=limit,
            prev=prev_link,
            next=next_link,
        ),
    )


@router.get(
    "/analytics",
    response_model=SuccessResponse[BadgeAnalyticsResponse],
    status_code=status.HTTP_200_OK,
    summary="Get organiser badge analytics",
    description=(
        "Returns aggregated metrics across all badges owned by the "
        "authenticated organiser. Includes total badge count, active "
        "(published) badge count, total share interactions, total badges "
        "created from public pages, and a per-platform-template usage "
        "breakdown. Soft-deleted badges are excluded from every aggregate."
    ),
    responses={
        200: {
            "description": "Analytics retrieved successfully.",
            "content": {
                "application/json": {
                    "example": {
                        "status": "success",
                        "message": "Analytics retrieved successfully.",
                        "data": {
                            "total_organiser_badges": 4,
                            "total_active_badges": 2,
                            "total_draft_badges": 2,
                            "total_shares": 87,
                            "total_badges_created": 152,
                            "platform_template_usage": [
                                {
                                    "platform_template_id": (
                                        "019e1b66-c4ec-7b80-8c85-84c2fe4f9c00"
                                    ),
                                    "count": 3,
                                },
                                {
                                    "platform_template_id": (
                                        "019e1b66-c4ec-7b80-8c85-84c2fe4f9c11"
                                    ),
                                    "count": 1,
                                },
                            ],
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
async def get_analytics(
    request: Request,
    session: DBSession,
    current_user: CurrentUser,
) -> SuccessResponse[BadgeAnalyticsResponse]:
    """Return aggregated badge metrics for the authenticated organiser."""
    (
        total,
        active,
        total_shares,
        total_creations,
        usage_rows,
    ) = await get_badge_analytics(session=session, organiser_id=current_user.id)

    return SuccessResponse(
        message="Analytics retrieved successfully.",
        data=BadgeAnalyticsResponse(
            total_organiser_badges=total,
            total_active_badges=active,
            total_shares=total_shares,
            total_badges_created=total_creations,
            platform_template_usage=[
                PlatformTemplateUsage(platform_template_id=tid, count=count)
                for tid, count in usage_rows
            ],
        ),
    )


@router.get(
    "/{id}",
    response_model=SuccessResponse[BadgeDetailResponse],
    status_code=status.HTTP_200_OK,
    summary="Get a single badge by ID",
    description=(
        "Returns the full detail of a single badge owned by the "
        "authenticated organiser. Useful for populating the edit form. "
        "Returns 404 for soft-deleted badges and 403 if the badge "
        "belongs to another organiser."
    ),
    responses={
        200: {"description": "Badge retrieved successfully."},
        401: {"model": ErrorResponse, "description": "Unauthenticated."},
        403: {"model": ErrorResponse, "description": "Not the badge owner."},
        404: {"model": ErrorResponse, "description": "Badge not found."},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded."},
    },
)
@limiter.limit("60/minute")
async def get_single_badge(
    request: Request,
    session: DBSession,
    current_user: CurrentUser,
    id: UUID,
) -> SuccessResponse[BadgeDetailResponse]:
    """Return a single badge by ID for the authenticated organiser."""
    try:
        badge = await get_badge_by_id(
            session=session,
            organiser_id=current_user.id,
            id=id,
        )
    except BadgeNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Badge not found.",
        ) from exc
    except NotBadgeOwnerError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not own this badge.",
        ) from exc

    return SuccessResponse(
        message="Badge retrieved successfully.",
        data=BadgeDetailResponse.model_validate(badge),
    )


@router.post(
    "/{id}/publish",
    response_model=SuccessResponse[PublishedBadgeResponse],
    status_code=status.HTTP_200_OK,
    summary="Publish a badge",
    description=(
        "Publishes the organiser's badge. Sets is_published to true, "
        "records the publish time, and generates a unique share slug on "
        "first publish. The slug is preserved across re-publishes."
    ),
    responses={
        200: {"description": "Badge published."},
        401: {"model": ErrorResponse, "description": "Unauthenticated."},
        403: {"model": ErrorResponse, "description": "Not the badge owner."},
        404: {"model": ErrorResponse, "description": "Badge not found."},
        409: {"model": ErrorResponse, "description": "Badge is already published."},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded."},
    },
)
@limiter.limit("30/minute")
async def publish(
    request: Request,
    session: DBSession,
    current_user: CurrentUser,
    id: UUID,
) -> SuccessResponse[PublishedBadgeResponse]:
    """Publish a badge."""
    try:
        badge = await publish_badge(
            session=session,
            organiser_id=current_user.id,
            id=id,
        )
    except BadgeNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Badge not found.",
        ) from exc
    except NotBadgeOwnerError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not own this badge.",
        ) from exc
    except BadgeAlreadyPublishedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Badge is already published.",
        ) from exc

    return SuccessResponse(
        message="Badge published successfully.",
        data=PublishedBadgeResponse.model_validate(badge),
    )


@router.post(
    "/{id}/unpublish",
    response_model=SuccessResponse[PublishedBadgeResponse],
    status_code=status.HTTP_200_OK,
    summary="Unpublish a badge",
    description=(
        "Unpublishes the organiser's badge. Sets is_published to false. "
        "The share slug is preserved so re-publishing later keeps the same URL."
    ),
    responses={
        200: {"description": "Badge unpublished."},
        401: {"model": ErrorResponse, "description": "Unauthenticated."},
        403: {"model": ErrorResponse, "description": "Not the badge owner."},
        404: {"model": ErrorResponse, "description": "Badge not found."},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded."},
    },
)
@limiter.limit("30/minute")
async def unpublish(
    request: Request,
    session: DBSession,
    current_user: CurrentUser,
    id: UUID,
) -> SuccessResponse[PublishedBadgeResponse]:
    """Unpublish a badge."""
    try:
        badge = await unpublish_badge(
            session=session,
            organiser_id=current_user.id,
            id=id,
        )
    except BadgeNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Badge not found.",
        ) from exc
    except NotBadgeOwnerError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not own this badge.",
        ) from exc

    return SuccessResponse(
        message="Badge unpublished successfully.",
        data=PublishedBadgeResponse.model_validate(badge),
    )


@router.post(
    "/{id}/duplicate",
    response_model=SuccessResponse[DuplicateBadgeResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Duplicate a badge",
    description=(
        "Creates a draft copy of the organiser's badge. "
        "The copy receives a new unique ID, inherits all configuration "
        "fields and hashtags from the original, and starts in an unpublished state. "
        "The original badge is not modified."
    ),
    responses={
        201: {"description": "Draft copy created."},
        401: {"model": ErrorResponse, "description": "Unauthenticated."},
        403: {"model": ErrorResponse, "description": "Not the badge owner."},
        404: {"model": ErrorResponse, "description": "Badge not found."},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded."},
    },
)
@limiter.limit("30/minute")
async def duplicate(
    request: Request,
    session: DBSession,
    current_user: CurrentUser,
    id: UUID,
) -> SuccessResponse[DuplicateBadgeResponse]:
    """Duplicate a badge into a new draft."""
    try:
        copy = await duplicate_badge(
            session=session,
            organiser_id=current_user.id,
            id=id,
        )
    except BadgeNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Badge not found.",
        ) from exc
    except NotBadgeOwnerError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not own this badge.",
        ) from exc

    return SuccessResponse(
        message="Badge duplicated successfully.",
        data=DuplicateBadgeResponse.model_validate(copy),
    )


@router.delete(
    "/{id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a badge",
    description=(
        "Permanently removes the badge and all associated records "
        "(badges, hashtags) from the database. The Cloudinary logo and any "
        "generated badge image assets are also deleted on a best-effort basis — "
        "a Cloudinary failure does not cause the request to fail. "
        "This action is irreversible."
    ),
    responses={
        204: {"description": "Badge deleted successfully."},
        401: {"model": ErrorResponse, "description": "Unauthenticated."},
        403: {"model": ErrorResponse, "description": "Not the badge owner."},
        404: {"model": ErrorResponse, "description": "Badge not found."},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded."},
    },
)
@limiter.limit("30/minute")
async def remove_badge(
    request: Request,
    session: DBSession,
    current_user: CurrentUser,
    id: UUID,
) -> None:
    """Permanently delete a badge and its Cloudinary assets."""
    try:
        await delete_badge(
            session=session,
            organiser_id=current_user.id,
            id=id,
        )
    except BadgeNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Badge not found.",
        ) from exc
    except NotBadgeOwnerError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not own this badge.",
        ) from exc


@router.patch(
    "/{id}",
    response_model=SuccessResponse[BadgeDetailResponse],
    status_code=status.HTTP_200_OK,
    summary="Edit a badge",
    description=(
        "Partially updates a badge. Only fields present in the "
        "request body are written to the database — absent fields are left "
        "unchanged. To clear a nullable field send it explicitly as null. "
        "To replace hashtags include the full desired list; omit the key "
        "entirely to leave hashtags unchanged. Returns the full updated badge."
    ),
    responses={
        200: {"description": "Badge updated successfully."},
        401: {"model": ErrorResponse, "description": "Unauthenticated."},
        403: {"model": ErrorResponse, "description": "Not the badge owner."},
        404: {"model": ErrorResponse, "description": "Badge not found."},
        422: {"model": ErrorResponse, "description": "Validation error."},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded."},
    },
)
@limiter.limit("30/minute")
async def update_badge(
    request: Request,
    session: DBSession,
    current_user: CurrentUser,
    id: UUID,
    payload: EditBadgeRequest,
) -> SuccessResponse[BadgeDetailResponse]:
    """Apply a partial update to a badge."""
    field_updates = payload.model_dump(exclude_unset=True)
    new_hashtags: list[str] | None = field_updates.pop("hashtags", None)
    update_hashtags: bool = "hashtags" in payload.model_fields_set

    try:
        badge = await edit_badge(
            session=session,
            organiser_id=current_user.id,
            id=id,
            field_updates=field_updates,
            new_hashtags=new_hashtags,
            update_hashtags=update_hashtags,
        )
    except BadgeNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Badge not found.",
        ) from exc
    except NotBadgeOwnerError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not own this badge.",
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc

    return SuccessResponse(
        message="Badge updated successfully.",
        data=BadgeDetailResponse.model_validate(badge),
    )


@router.put(
    "/{id}/logo",
    response_model=SuccessResponse[LogoUploadResponse],
    status_code=status.HTTP_200_OK,
    summary="Upload a logo for a badge",
    description=(
        "Accepts a multipart/form-data upload with a single PNG or JPG image "
        "(max 2 MB). Stores the file in Cloudinary under the badge-logos/ "
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
                            "logo_url": "https://res.cloudinary.com/demo/image/upload/badge-logos/abc.png"
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
        404: {"model": ErrorResponse, "description": "Badge not found."},
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
    id: UUID,
    request: Request,
    session: DBSession,
    current_user: CurrentUser,
    file: Annotated[UploadFile, File()],
) -> SuccessResponse[LogoUploadResponse]:
    """Upload or replace the logo for a badge."""
    if file.content_type not in _ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Unsupported file type. Only PNG, JPG, and SVG images are allowed.",
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
            detail="Unsupported file type. Only PNG, JPG, and SVG images are allowed.",
        )

    try:
        logo_url = await upload_badge_logo(
            session=session,
            id=id,
            organiser_id=current_user.id,
            image_data=image_data,
        )
    except BadgeNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Badge not found.",
        ) from exc
    except NotBadgeOwnerError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to modify this badge.",
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
    "/public/{slug}",
    response_model=SuccessResponse[PublicBadgePageResponse],
    status_code=status.HTTP_200_OK,
    summary="Get public participant page data",
    description=(
        "Returns the public-facing badge data needed to render the participant "
        "page. No authentication required. Only returns data for published "
        "templates — unpublished slugs return 404. Exposes only the fields "
        "needed for public rendering, not organiser configuration internals."
    ),
    responses={
        200: {
            "description": "Published badge data.",
            "content": {
                "application/json": {
                    "example": {
                        "status": "success",
                        "message": "Badge data retrieved successfully.",
                        "data": {
                            "title": "HNG Tech Fest 2026",
                            "canvas_data": {"layout": "bold-v1"},
                            "logo_url": "https://res.cloudinary.com/demo/image/upload/badge-logos/abc.png",
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
            "description": "Slug not found or badge is not published.",
        },
        429: {"model": ErrorResponse, "description": "Rate limit exceeded."},
    },
)
@limiter.limit("60/minute")
async def get_participant_page(
    request: Request,
    session: DBSession,
    slug: str,
) -> SuccessResponse[PublicBadgePageResponse]:
    """Return public-facing badge data for the participant page."""
    try:
        badge = await get_public_badge_by_slug(
            session=session,
            slug=slug,
        )
    except PublicBadgeNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Badge not found.",
        ) from exc

    return SuccessResponse(
        message="Badge data retrieved successfully.",
        data=PublicBadgePageResponse(
            title=badge.title,
            access_type=badge.access_type,
            canvas_data=badge.canvas_data,
            logo_url=badge.logo_url,
            default_caption=badge.default_caption,
            destination_link=badge.destination_link,
            hashtags=[h.hashtag for h in badge.hashtags],
        ),
    )


@router.post(
    "/public/{slug}/increment-creation",
    response_model=SuccessResponse[None],
    status_code=status.HTTP_200_OK,
    summary="Increment badge creation count",
    description=(
        "Records that a participant has generated a badge from the public page. "
        "No authentication required. Increments creation_count atomically at the "
        "database level. Returns 404 if the slug does not resolve to a published badge."
    ),
    responses={
        200: {"description": "Creation count incremented."},
        404: {
            "model": ErrorResponse,
            "description": "Slug not found or badge is not published.",
        },
        429: {"model": ErrorResponse, "description": "Rate limit exceeded."},
    },
)
@limiter.limit("60/minute")
async def increment_creation(
    request: Request,
    session: DBSession,
    slug: str,
) -> SuccessResponse[None]:
    """Atomically increment the creation counter for a public badge."""
    try:
        await increment_badge_creation_count(session=session, slug=slug)
    except PublicBadgeNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Badge not found.",
        ) from exc

    return SuccessResponse(message="Creation count incremented.")


@router.post(
    "/public/{slug}/increment-share",
    response_model=SuccessResponse[None],
    status_code=status.HTTP_200_OK,
    summary="Increment badge share count",
    description=(
        "Records that a participant has shared a badge. "
        "Intended to be called by the FE when a share action actually occurs "
        "(not on every page load). The increment runs as a background task so "
        "the response returns immediately. Returns 404 if the slug does not "
        "resolve to a published badge."
    ),
    responses={
        200: {"description": "Share count increment scheduled."},
        404: {
            "model": ErrorResponse,
            "description": "Slug not found or badge is not published.",
        },
        429: {"model": ErrorResponse, "description": "Rate limit exceeded."},
    },
)
@limiter.limit("60/minute")
async def increment_share(
    request: Request,
    session: DBSession,
    slug: str,
    background_tasks: BackgroundTasks,
) -> SuccessResponse[None]:
    """Atomically increment the share counter for a public badge."""
    try:
        await get_public_badge_by_slug(session=session, slug=slug)
    except PublicBadgeNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Badge not found.",
        ) from exc

    background_tasks.add_task(increment_badge_share_count, session, slug)

    return SuccessResponse(message="Share count increment scheduled.")


@router.post(
    "/public/{slug}/validate-access",
    response_model=SuccessResponse[None],
    status_code=status.HTTP_200_OK,
    summary="Validate participant access code",
    description=(
        "Verifies whether a participant's submitted access code matches the "
        "organiser-defined access code for a private badge. Returns 404 if the slug "
        "does not resolve to a published badge. "
        "If the badge is public, validation is bypassed and 200 OK is returned."
    ),
    responses={
        200: {"description": "Access code is valid or badge is public."},
        403: {"model": ErrorResponse, "description": "Invalid access code."},
        404: {
            "model": ErrorResponse,
            "description": "Slug not found or badge is not published.",
        },
        429: {"model": ErrorResponse, "description": "Rate limit exceeded."},
    },
)
@limiter.limit("60/minute")
async def validate_badge_access(
    request: Request,
    session: DBSession,
    slug: str,
    payload: ValidateAccessRequest,
) -> SuccessResponse[None]:
    """Validate the access code for a private badge."""
    try:
        badge = await get_public_badge_by_slug(session=session, slug=slug)
    except PublicBadgeNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Badge not found.",
        ) from exc

    if badge.access_type == 0:
        return SuccessResponse(message="Access granted. This badge is public.")

    if badge.access_type == 1:
        if not badge.access_code:
            # Failsafe: if a private badge somehow has no access code, fail closed.
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid access code.",
            )

        expected = badge.access_code.strip().lower()
        provided = payload.access_code.strip().lower()

        if expected != provided:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid access code.",
            )

        return SuccessResponse(message="Access code is valid.")

    # Unhandled access_type fallback
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Invalid access configuration.",
    )
