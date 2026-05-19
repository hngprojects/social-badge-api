"""Admin endpoints for platform template management."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.core.rate_limit import limiter
from app.dependencies import DBSession, get_current_admin
from fastapi import APIRouter, HTTPException, Request, status

from app.core.rate_limit import limiter
from app.dependencies import DBSession
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
    update_platform_template,
)

router = APIRouter(dependencies=[Depends(get_current_admin)])
router = APIRouter()
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
    """Create a new platform template."""
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
    """Update fields on a platform template."""
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
    """Delete a platform template."""
    template = await get_platform_template(session=session, template_id=template_id)
    if template is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Platform template not found.",
        )
    await delete_platform_template(session=session, template=template)
    return SuccessResponse(message="Platform template deleted successfully.")
