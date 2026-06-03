from fastapi import APIRouter, HTTPException, Request, status

from app.core.rate_limit import limiter
from app.dependencies import CurrentUser, DBSession
from app.schemas.notification import (
    NotificationPreferencesResponse,
    UpdateNotificationPreferencesRequest,
)
from app.schemas.response import ErrorResponse, SuccessResponse
from app.services.notification import (
    get_notification_preferences,
    update_notification_preferences,
)

router = APIRouter()


@router.get(
    "",
    response_model=SuccessResponse[NotificationPreferencesResponse],
    status_code=status.HTTP_200_OK,
    summary="Get notification preferences",
    description=(
        "Returns the authenticated organiser's current notification preferences. "
        "Organisers who have never saved preferences receive the defaults "
        "(all notifications on) rather than a 404."
    ),
    responses={
        200: {"description": "Preferences retrieved."},
        401: {"model": ErrorResponse, "description": "Not authenticated."},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded."},
    },
)
@limiter.limit("30/minute")
async def get_preferences(
    request: Request,
    session: DBSession,
    current_user: CurrentUser,
) -> SuccessResponse[NotificationPreferencesResponse]:
    """Return the current organiser's notification preferences."""
    prefs = await get_notification_preferences(
        session=session,
        user_id=current_user.id,
    )
    return SuccessResponse(
        message="Notification preferences retrieved successfully.",
        data=prefs,
    )


@router.patch(
    "",
    response_model=SuccessResponse[NotificationPreferencesResponse],
    status_code=status.HTTP_200_OK,
    summary="Update notification preferences",
    description=(
        "Partially updates the authenticated organiser's notification preferences. "
        "Only fields present in the request body are written — absent fields are "
        "left unchanged. Unknown keys are silently ignored. "
        "An empty body returns 400."
    ),
    responses={
        200: {"description": "Preferences updated."},
        400: {
            "model": ErrorResponse,
            "description": "Request body contains no known preference fields.",
        },
        401: {"model": ErrorResponse, "description": "Not authenticated."},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded."},
    },
)
@limiter.limit("30/minute")
async def patch_preferences(
    request: Request,
    session: DBSession,
    current_user: CurrentUser,
    payload: UpdateNotificationPreferencesRequest | None = None,
) -> SuccessResponse[NotificationPreferencesResponse]:
    """Apply a partial update to the organiser's notification preferences."""
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Request body must include at least one preference field.",
        )

    # Strip fields the client left as None (not sent).
    updates = {key: val for key, val in payload.model_dump().items() if val is not None}

    if not updates:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Request body must include at least one preference field.",
        )

    prefs = await update_notification_preferences(
        session=session,
        user_id=current_user.id,
        updates=updates,
    )
    return SuccessResponse(
        message="Notification preferences updated successfully.",
        data=prefs,
    )
