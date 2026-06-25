from urllib.parse import urlencode
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, status

from app.core.exceptions import PlatformTemplateNotFoundError
from app.core.rate_limit import limiter
from app.dependencies import DBSession
from app.schemas.platform_template import (
    PlatformTemplateListResponse,
    PlatformTemplateResponse,
)
from app.schemas.response import ErrorResponse, SuccessResponse
from app.services.badge import (
    get_platform_template,
    list_platform_templates,
)

router = APIRouter()


@router.get(
    "",
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
                        "message": ("Platform templates retrieved successfully."),
                        "data": {
                            "templates": [
                                {
                                    "id": ("019e1b66-c4ec-7b80-8c85-84c2fe4f9c84"),
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
        429: {
            "model": ErrorResponse,
            "description": "Rate limit exceeded.",
        },
    },
)
@limiter.limit("60/minute")
async def list_templates(
    request: Request,
    session: DBSession,
    category: str | None = Query(
        default=None,
        description=(
            "Gallery tab filter. One of: festivals, hackathons, "
            "conferences, community, bootcamp, meetups, speakers, "
            "trending."
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
    """
    Returns active platform templates with pagination and an optional category filter.

    Fetches a paginated set of active platform templates from the database, utilizing OFFSET and LIMIT constraints. This is a public gallery endpoint requiring no authentication and is rate-limited to 60 requests per minute per IP address.
    """
    normalised_category = category.strip().lower() if category is not None else None
    if normalised_category == "":
        normalised_category = None

    try:
        templates, total = await list_platform_templates(
            session,
            category=normalised_category,
            page=page,
            limit=limit,
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
    "/{id}",
    response_model=SuccessResponse[PlatformTemplateResponse],
    status_code=status.HTTP_200_OK,
    summary="Get a single platform template",
    description=(
        "Returns the full platform template detail, including canvas_data. "
        "Used to populate the live preview panel when an organiser clicks a "
        "gallery card. No authentication required."
    ),
    responses={
        200: {
            "description": "Platform template retrieved successfully.",
        },
        404: {
            "model": ErrorResponse,
            "description": "Platform template not found or inactive.",
        },
        422: {
            "model": ErrorResponse,
            "description": "Validation error on query parameters.",
        },
        429: {
            "model": ErrorResponse,
            "description": "Rate limit exceeded.",
        },
    },
)
@limiter.limit("60/minute")
async def get_badge(
    request: Request,
    session: DBSession,
    id: UUID,
) -> SuccessResponse[PlatformTemplateResponse]:
    """
    Retrieves a single active platform template by its unique ID.

    Fetches the details and canvas data of the template to populate layout design previews. This is a public endpoint requiring no authentication, performs a fast single-row primary key database lookup, and is rate-limited to 60 requests per minute per IP address.
    """
    try:
        template = await get_platform_template(session, id)
    except PlatformTemplateNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Platform template not found.",
        ) from exc

    return SuccessResponse(
        message="Platform template retrieved successfully.",
        data=PlatformTemplateResponse.model_validate(template),
    )
