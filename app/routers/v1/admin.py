from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.core.rate_limit import limiter
from app.dependencies import DBSession, get_current_admin
from app.schemas.admin import (
    CreatePlatformTemplateRequest,
    PlatformTemplateResponse,
    UpdatePlatformTemplateRequest,
)
from app.schemas.response import ErrorResponse, SuccessResponse
from app.services.admin import (
    create_platform_template,
    delete_platform_template,
    get_platform_template,
    list_platform_templates,
    update_platform_template,
)

router = APIRouter(dependencies=[Depends(get_current_admin)])
"""Admin API router for platform templates."""


@router.post(
    "/platform-templates",
    response_model=SuccessResponse[PlatformTemplateResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create a platform template",
    responses={
        201: {"description": "Platform template created."},
        429: {
            "model": ErrorResponse,
            "description": "Rate limit exceeded.",
            "content": {
                "application/json": {
                    "example": {"status": "error", "message": "Rate limit exceeded."}
                }
            },
        },
    },
)
@limiter.limit("30/minute")
async def create_template(
    request: Request,
    session: DBSession,
    payload: CreatePlatformTemplateRequest,
) -> SuccessResponse[PlatformTemplateResponse]:
    """Creates a new platform design template available to organisers for badge layout
    customization.

    This endpoint requires admin authorization privileges and is limited to users with
    the 'admin' role. The handler performs an INSERT operation on the platform templates
    database table and commits the transaction immediately, subject to a rate limit of
    30 requests per minute per IP.
    """
    template = await create_platform_template(
        session=session,
        title=payload.title,
        category=payload.category,
        canvas_data=payload.canvas_data,
        thumbnail_url=payload.thumbnail_url,
        is_active=payload.is_active,
    )
    return SuccessResponse(
        message="Platform template created successfully.",
        data=PlatformTemplateResponse.model_validate(template),
    )


@router.patch(
    "/platform-templates/{template_id}",
    response_model=SuccessResponse[PlatformTemplateResponse],
    status_code=status.HTTP_200_OK,
    summary="Update a platform template",
    responses={
        200: {"description": "Platform template updated."},
        404: {
            "model": ErrorResponse,
            "description": "Template not found.",
            "content": {
                "application/json": {
                    "example": {
                        "status": "error",
                        "message": "Platform template not found.",
                    }
                }
            },
        },
        429: {
            "model": ErrorResponse,
            "description": "Rate limit exceeded.",
            "content": {
                "application/json": {
                    "example": {"status": "error", "message": "Rate limit exceeded."}
                }
            },
        },
    },
)
@limiter.limit("30/minute")
async def update_template(
    request: Request,
    session: DBSession,
    template_id: UUID,
    payload: UpdatePlatformTemplateRequest,
) -> SuccessResponse[PlatformTemplateResponse]:
    """Updates the details of an existing platform design template.

    Modifies attributes such as layout variables, category, title, or active state for a
    template queryable by its ID. It requires admin authorization, queries the database
    for the template, updates target fields, and commits the transaction with a rate
    limit of 30 requests per minute per IP.
    """
    template = await get_platform_template(session=session, template_id=template_id)
    if template is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Platform template not found.",
        )
    updated = await update_platform_template(
        session=session,
        template=template,
        title=payload.title,
        category=payload.category,
        canvas_data=payload.canvas_data,
        thumbnail_url=payload.thumbnail_url,
        is_active=payload.is_active,
    )
    return SuccessResponse(
        message="Platform template updated successfully.",
        data=PlatformTemplateResponse.model_validate(updated),
    )


@router.delete(
    "/platform-templates/{template_id}",
    response_model=SuccessResponse[None],
    status_code=status.HTTP_200_OK,
    summary="Delete a platform template",
    responses={
        200: {"description": "Platform template deleted."},
        404: {
            "model": ErrorResponse,
            "description": "Template not found.",
            "content": {
                "application/json": {
                    "example": {
                        "status": "error",
                        "message": "Platform template not found.",
                    }
                }
            },
        },
        429: {
            "model": ErrorResponse,
            "description": "Rate limit exceeded.",
            "content": {
                "application/json": {
                    "example": {"status": "error", "message": "Rate limit exceeded."}
                }
            },
        },
    },
)
@limiter.limit("30/minute")
async def delete_template(
    request: Request,
    session: DBSession,
    template_id: UUID,
) -> SuccessResponse[None]:
    """Deletes a platform design template by removing its record from the database.

    Requires admin authorization privileges to proceed. The handler executes a database
    fetch followed by a DELETE query under a rate limit of 30 requests per minute per
    IP.
    """
    template = await get_platform_template(session=session, template_id=template_id)
    if template is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Platform template not found.",
        )
    await delete_platform_template(session=session, template=template)
    return SuccessResponse(message="Platform template deleted successfully.")


@router.get(
    "/platform-templates",
    response_model=SuccessResponse[list[PlatformTemplateResponse]],
    status_code=status.HTTP_200_OK,
    summary="List platform templates",
)
@limiter.limit("30/minute")
async def list_templates(
    request: Request,
    session: DBSession,
    category: str | None = Query(None),
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> SuccessResponse[list[PlatformTemplateResponse]]:
    """Lists platform design templates, optionally filtered by category.

    Retrieves a listing of platform templates for administration and management. This
    query executes with offset and limit pagination over the platform templates table,
    requires admin authorization, and is rate-limited to 30 requests per minute per IP.
    """
    templates = await list_platform_templates(
        session=session, category=category, limit=limit, offset=offset
    )
    return SuccessResponse(
        message="Platform templates retrieved successfully.",
        data=[PlatformTemplateResponse.model_validate(t) for t in templates],
    )


@router.get(
    "/platform-templates/{template_id}",
    response_model=SuccessResponse[PlatformTemplateResponse],
    status_code=status.HTTP_200_OK,
    summary="Get a platform template",
    responses={
        404: {
            "model": ErrorResponse,
            "description": "Template not found.",
            "content": {
                "application/json": {
                    "example": {
                        "status": "error",
                        "message": "Platform template not found.",
                    }
                }
            },
        },
    },
)
@limiter.limit("30/minute")
async def get_template(
    request: Request,
    session: DBSession,
    template_id: UUID,
) -> SuccessResponse[PlatformTemplateResponse]:
    """Retrieves the full design configuration details of a platform template by its ID.

    This operation requires admin authorization privileges and executes a single-row
    database read using the primary key. It is rate-limited to 30 requests per minute
    per IP.
    """
    template = await get_platform_template(session=session, template_id=template_id)
    if template is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Platform template not found.",
        )
    return SuccessResponse(
        message="Platform template retrieved successfully.",
        data=PlatformTemplateResponse.model_validate(template),
    )
